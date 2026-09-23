from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from .common import TASKS_ROOT, load_json, repository_hash, write_json
    from .git_start_state import inspect_start_commit
    from .api_wrapper.tools import (
        ClarificationPolicy,
        ClarificationResolution,
        resolve_clarification_request,
    )
except ImportError:  # Supports direct script execution.
    from common import TASKS_ROOT, load_json, repository_hash, write_json  # type: ignore
    from git_start_state import inspect_start_commit  # type: ignore
    from api_wrapper.tools import (  # type: ignore
        ClarificationPolicy,
        ClarificationResolution,
        resolve_clarification_request,
    )


RECORD_RELATIVE_PATH = Path("native_ide") / "run_record.json"
JOURNAL_RELATIVE_PATH = Path("native_ide") / "timing_events.jsonl"
PERMISSION_RELATIVE_PATH = Path("native_ide") / "permission_events.jsonl"
CLARIFICATION_RELATIVE_PATH = Path("native_ide") / "clarification_events.jsonl"
RECORD_STATES = {"prepared", "running", "frozen"}
STOP_REASONS = {
    "submitted",
    "task_wall_clock_limit",
    "infrastructure_failure",
}
PERMISSION_TYPES = {"terminal_command", "workspace_file_change", "network_access", "other"}
PERMISSION_DECISIONS = {"approved", "denied"}
PERMISSION_SCOPES = {"single_action", "session", "persistent", "unknown"}
HEX_64 = re.compile(r"[0-9a-f]{64}")


class NativeRunRecorderError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise NativeRunRecorderError("Recorder timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _object_sha256(value: dict[str, Any], excluded_key: str) -> str:
    payload = {key: item for key, item in value.items() if key != excluded_key}
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _atomic_write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    write_json(temporary, value)
    temporary.replace(path)


def _read_journal(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise NativeRunRecorderError(
                f"Invalid timing journal line {line_number}: {error.msg}"
            ) from error
        if not isinstance(value, dict):
            raise NativeRunRecorderError(
                f"Timing journal line {line_number} is not an object"
            )
        records.append(value)
    return records


def _append_event(
    path: Path,
    *,
    event_type: str,
    run_id: str,
    recorded_at: str,
    monotonic_ns: int,
    details: dict[str, Any],
) -> dict[str, Any]:
    records = _read_journal(path)
    previous_hash = records[-1]["event_sha256"] if records else None
    event = {
        "schema_version": "1.0.0",
        "sequence": len(records) + 1,
        "event_type": event_type,
        "run_id": run_id,
        "recorded_at": recorded_at,
        "monotonic_ns": monotonic_ns,
        "details": details,
        "previous_event_sha256": previous_hash,
        "event_sha256": None,
    }
    event["event_sha256"] = _object_sha256(event, "event_sha256")
    temporary = path.with_name(path.name + ".tmp")
    text = "".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
        for item in [*records, event]
    )
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return event


def _chain_head(path: Path) -> str | None:
    records = _read_journal(path)
    return records[-1]["event_sha256"] if records else None


def _validate_chain(
    records: list[dict[str, Any]], label: str, issues: list[str]
) -> None:
    previous: str | None = None
    for sequence, event in enumerate(records, 1):
        if event.get("sequence") != sequence:
            issues.append(f"{label} sequence is not contiguous")
        if event.get("previous_event_sha256") != previous:
            issues.append(f"{label} previous hash mismatch")
        if event.get("event_sha256") != _object_sha256(event, "event_sha256"):
            issues.append(f"{label} event hash mismatch")
        previous = event.get("event_sha256")


def _require_running_record(
    evidence_directory: Path,
) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    metadata_path, metadata = _load_native_metadata(evidence_directory)
    record_path = evidence_directory / RECORD_RELATIVE_PATH
    record = load_json(record_path)
    if record.get("record_state") != "running" or metadata.get("lifecycle_state") != "running":
        raise NativeRunRecorderError("Evidence events may be recorded only while the run is running")
    return metadata_path, metadata, record_path, record


def _assert_existing_record_valid(
    evidence_directory: Path, workspace: Path | None = None
) -> None:
    issues = validate_record(evidence_directory, workspace)
    if issues:
        raise NativeRunRecorderError(
            "Existing native evidence is invalid: " + "; ".join(issues)
        )


def _running_event_anchor(
    record: dict[str, Any],
    now: Callable[[], datetime],
    monotonic_ns: Callable[[], int],
) -> tuple[str, int]:
    recorded_at = _utc_text(now())
    observed = monotonic_ns()
    started = record["timing"].get("monotonic_start_ns")
    limit = record["limit"].get("task_wall_clock_seconds")
    if not isinstance(started, int) or observed < started:
        raise NativeRunRecorderError("Monotonic event time is invalid")
    if isinstance(limit, int) and observed - started >= limit * 1_000_000_000:
        raise NativeRunRecorderError(
            "Task wall-clock limit has been reached; stop and freeze the run before recording more events"
        )
    return recorded_at, observed


def _set_evidence_head(
    record: dict[str, Any], label: str, event: dict[str, Any]
) -> None:
    record["evidence_chain_heads"][label] = event["event_sha256"]
    record["record_sha256"] = _object_sha256(record, "record_sha256")


def _clarification_log_value(
    metadata: dict[str, Any], *, status: str, events: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "status": status,
        "run_id": metadata["run_id"],
        "task_id": metadata["task"]["task_id"],
        "clarification_opportunity": metadata["clarification"]["opportunity"],
        "events": events,
    }


def _load_native_metadata(evidence_directory: Path) -> tuple[Path, dict[str, Any]]:
    metadata_path = evidence_directory.resolve() / "metadata.json"
    metadata = load_json(metadata_path)
    if metadata.get("system", {}).get("evaluation_interface") != "native_ide":
        raise NativeRunRecorderError("Run is not configured for the native-IDE interface")
    if metadata.get("system", {}).get("system_id") not in {"cursor", "devin"}:
        raise NativeRunRecorderError("Native recorder supports only Cursor and Devin")
    return metadata_path, metadata


def prepare_record(
    evidence_directory: Path,
    workspace: Path,
    *,
    native_freeze_id: str,
    product_version: str,
    displayed_model_or_mode: str,
    configuration_sha256: str,
    order_position: int,
    random_seed: str,
    task_wall_clock_seconds: int,
    profile_name: str = "TSB Evaluation",
    now: Callable[[], datetime] = _utc_now,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> dict[str, Any]:
    evidence_directory = evidence_directory.resolve()
    workspace = workspace.resolve()
    metadata_path, metadata = _load_native_metadata(evidence_directory)
    if metadata.get("lifecycle_state") != "prepared":
        raise NativeRunRecorderError("Record preparation requires a prepared run")
    record_path = evidence_directory / RECORD_RELATIVE_PATH
    journal_path = evidence_directory / JOURNAL_RELATIVE_PATH
    if record_path.exists() or journal_path.exists():
        raise NativeRunRecorderError("Refusing to overwrite an existing native run record")
    required_text = {
        "native_freeze_id": native_freeze_id,
        "product_version": product_version,
        "displayed_model_or_mode": displayed_model_or_mode,
        "profile_name": profile_name,
        "random_seed": random_seed,
    }
    for label, value in required_text.items():
        if not isinstance(value, str) or not value.strip():
            raise NativeRunRecorderError(f"{label} must be a non-empty string")
    if not isinstance(configuration_sha256, str) or not HEX_64.fullmatch(
        configuration_sha256
    ):
        raise NativeRunRecorderError("configuration_sha256 must be 64 lowercase hex characters")
    if isinstance(order_position, bool) or not isinstance(order_position, int) or not 1 <= order_position <= 4:
        raise NativeRunRecorderError("order_position must be an integer from 1 to 4")
    if (
        isinstance(task_wall_clock_seconds, bool)
        or not isinstance(task_wall_clock_seconds, int)
        or task_wall_clock_seconds <= 0
    ):
        raise NativeRunRecorderError("task_wall_clock_seconds must be a positive integer")

    head, clean = inspect_start_commit(workspace)
    if head != metadata["task"]["start_commit"] or not clean:
        raise NativeRunRecorderError("Workspace must be clean at the frozen start commit")
    task_id = metadata["task"]["task_id"]
    fixture_manifest = load_json(TASKS_ROOT / task_id / "fixture_manifest.json")
    observed_fixture = repository_hash(workspace, fixture_manifest)
    if observed_fixture != metadata["task"]["fixture_sha256"]:
        raise NativeRunRecorderError("Workspace content does not match the frozen fixture")

    recorded_at = _utc_text(now())
    mono = monotonic_ns()
    native_directory = record_path.parent
    native_directory.mkdir(parents=True, exist_ok=False)
    record: dict[str, Any] = {
        "schema_version": "1.0.0",
        "record_type": "native_ide_run",
        "run_id": metadata["run_id"],
        "task_id": task_id,
        "system_id": metadata["system"]["system_id"],
        "record_state": "prepared",
        "native_configuration": {
            "freeze_id": native_freeze_id.strip(),
            "product_version": product_version.strip(),
            "displayed_model_or_mode": displayed_model_or_mode.strip(),
            "configuration_sha256": configuration_sha256,
            "profile_name": profile_name.strip(),
        },
        "schedule": {
            "order_position": order_position,
            "random_seed": random_seed.strip(),
        },
        "workspace": {
            "start_commit": head,
            "fixture_sha256": observed_fixture,
            "final_head": None,
            "final_workspace_sha256": None,
        },
        "timing": {
            "clock_source": "time.monotonic_ns_with_utc_anchors",
            "prepared_at": recorded_at,
            "started_at": None,
            "ended_at": None,
            "monotonic_start_ns": None,
            "monotonic_end_ns": None,
            "elapsed_seconds": None,
            "wall_elapsed_seconds": None,
            "wall_minus_monotonic_seconds": None,
            "final_state_frozen_at": None,
        },
        "limit": {"task_wall_clock_seconds": task_wall_clock_seconds},
        "stopping": {
            "reason": None,
            "detail": None,
            "visible_completion_statement": None,
            "submission_signal": None,
        },
        "artifacts": {
            "task_prompt": metadata["artifacts"]["task_prompt"],
            "transcript": metadata["artifacts"]["transcript"],
            "timing_journal": JOURNAL_RELATIVE_PATH.as_posix(),
            "permission_journal": PERMISSION_RELATIVE_PATH.as_posix(),
            "clarification_journal": CLARIFICATION_RELATIVE_PATH.as_posix(),
            "clarification_log": metadata["artifacts"]["clarification_log"],
        },
        "evidence_chain_heads": {
            "permission_event_sha256": None,
            "clarification_event_sha256": None,
        },
        "record_sha256": None,
    }
    record["record_sha256"] = _object_sha256(record, "record_sha256")
    metadata["system"]["product_version"] = product_version.strip()
    metadata["system"]["model_identifier"] = displayed_model_or_mode.strip()
    metadata["system"]["configuration_sha256"] = configuration_sha256
    metadata["schedule"] = {
        "order_position": order_position,
        "random_seed": random_seed.strip(),
    }
    metadata["limits"]["task_wall_clock_seconds"] = task_wall_clock_seconds
    _append_event(
        journal_path,
        event_type="record_prepared",
        run_id=metadata["run_id"],
        recorded_at=recorded_at,
        monotonic_ns=mono,
        details={"record_state": "prepared", "start_commit": head},
    )
    (evidence_directory / PERMISSION_RELATIVE_PATH).write_text("", encoding="utf-8")
    (evidence_directory / CLARIFICATION_RELATIVE_PATH).write_text("", encoding="utf-8")
    _atomic_write_json(record_path, record)
    _atomic_write_json(metadata_path, metadata)
    return record


def start_run(
    evidence_directory: Path,
    workspace: Path,
    *,
    now: Callable[[], datetime] = _utc_now,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> dict[str, Any]:
    evidence_directory = evidence_directory.resolve()
    _assert_existing_record_valid(evidence_directory, workspace.resolve())
    metadata_path, metadata = _load_native_metadata(evidence_directory)
    record_path = evidence_directory / RECORD_RELATIVE_PATH
    journal_path = evidence_directory / JOURNAL_RELATIVE_PATH
    record = load_json(record_path)
    if record.get("record_state") != "prepared" or metadata.get("lifecycle_state") != "prepared":
        raise NativeRunRecorderError("Run can start exactly once from prepared state")
    head, clean = inspect_start_commit(workspace.resolve())
    if head != record["workspace"]["start_commit"] or not clean:
        raise NativeRunRecorderError("Workspace changed before the timed start")
    started_at = _utc_text(now())
    mono = monotonic_ns()
    record["record_state"] = "running"
    record["timing"]["started_at"] = started_at
    record["timing"]["monotonic_start_ns"] = mono
    record["record_sha256"] = _object_sha256(record, "record_sha256")
    metadata["lifecycle_state"] = "running"
    metadata["timing"] = {
        "started_at": started_at,
        "ended_at": None,
        "elapsed_seconds": None,
    }
    _atomic_write_json(
        evidence_directory / metadata["artifacts"]["clarification_log"],
        _clarification_log_value(metadata, status="running", events=[]),
    )
    _append_event(
        journal_path,
        event_type="task_brief_submitted",
        run_id=metadata["run_id"],
        recorded_at=started_at,
        monotonic_ns=mono,
        details={"record_state": "running"},
    )
    _atomic_write_json(record_path, record)
    _atomic_write_json(metadata_path, metadata)
    return record


def record_permission_event(
    evidence_directory: Path,
    *,
    prompt_text: str,
    permission_type: str,
    decision: str,
    scope: str,
    now: Callable[[], datetime] = _utc_now,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> dict[str, Any]:
    evidence_directory = evidence_directory.resolve()
    _assert_existing_record_valid(evidence_directory)
    _, metadata, record_path, record = _require_running_record(evidence_directory)
    if not isinstance(prompt_text, str) or not prompt_text.strip() or "\x00" in prompt_text:
        raise NativeRunRecorderError("permission prompt_text must be a non-empty string")
    if len(prompt_text) > 4096:
        raise NativeRunRecorderError("permission prompt_text exceeds 4096 characters")
    if permission_type not in PERMISSION_TYPES:
        raise NativeRunRecorderError(f"Unsupported permission type: {permission_type}")
    if decision not in PERMISSION_DECISIONS:
        raise NativeRunRecorderError(f"Unsupported permission decision: {decision}")
    if scope not in PERMISSION_SCOPES:
        raise NativeRunRecorderError(f"Unsupported permission scope: {scope}")
    recorded_at, observed_monotonic = _running_event_anchor(
        record, now, monotonic_ns
    )
    event = _append_event(
        evidence_directory / PERMISSION_RELATIVE_PATH,
        event_type="permission_decision",
        run_id=metadata["run_id"],
        recorded_at=recorded_at,
        monotonic_ns=observed_monotonic,
        details={
            "prompt_text": prompt_text.strip(),
            "permission_type": permission_type,
            "decision": decision,
            "scope": scope,
            "information_provided": False,
            "counts_as_clarification": False,
        },
    )
    _set_evidence_head(record, "permission_event_sha256", event)
    _atomic_write_json(record_path, record)
    return event


def record_clarification_request(
    evidence_directory: Path,
    *,
    request_text: str,
    now: Callable[[], datetime] = _utc_now,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> ClarificationResolution:
    evidence_directory = evidence_directory.resolve()
    _assert_existing_record_valid(evidence_directory)
    metadata_path, metadata, record_path, record = _require_running_record(
        evidence_directory
    )
    task_id = metadata["task"]["task_id"]
    policy_path = TASKS_ROOT / task_id / "clarification_policy.json"
    policy = ClarificationPolicy.load(policy_path) if policy_path.is_file() else None
    try:
        resolution = resolve_clarification_request(
            request_text,
            policy=policy,
            response_already_issued=metadata["clarification"]["responses"] >= 1,
        )
    except ValueError as error:
        raise NativeRunRecorderError(str(error)) from error
    recorded_at, observed_monotonic = _running_event_anchor(
        record, now, monotonic_ns
    )
    sequence = metadata["clarification"]["requests"] + 1
    call_id = f"native-clarification-{sequence:02d}"
    journal_event = _append_event(
        evidence_directory / CLARIFICATION_RELATIVE_PATH,
        event_type="clarification_request_resolved",
        run_id=metadata["run_id"],
        recorded_at=recorded_at,
        monotonic_ns=observed_monotonic,
        details={
            "sequence": sequence,
            "request_text": request_text.strip(),
            "authorized": resolution.authorized,
            "response_issued": resolution.response_issued,
            "response_card_id": resolution.response_card_id,
            "reason_code": resolution.reason_code,
            "delivered_text": resolution.response_text,
        },
    )
    log_path = evidence_directory / metadata["artifacts"]["clarification_log"]
    log = load_json(log_path)
    events = log.get("events")
    if not isinstance(events, list):
        raise NativeRunRecorderError("clarification_log.json events must be a list")
    events.append(
        {
            "event_type": "request",
            "sequence": sequence,
            "call_id": call_id,
            "request_text": request_text.strip(),
            "timestamp": recorded_at,
        }
    )
    events.append(
        {
            "event_type": "decision",
            "call_id": call_id,
            "authorized": resolution.authorized,
            "reason_code": resolution.reason_code,
            "timestamp": recorded_at,
        }
    )
    metadata["clarification"]["requests"] += 1
    if resolution.authorized:
        metadata["clarification"]["authorized_requests"] += 1
    if resolution.response_issued:
        metadata["clarification"]["responses"] += 1
        events.append(
            {
                "event_type": "response",
                "call_id": call_id,
                "response_card_id": resolution.response_card_id,
                "timestamp": recorded_at,
            }
        )
    _set_evidence_head(record, "clarification_event_sha256", journal_event)
    _atomic_write_json(
        log_path, _clarification_log_value(metadata, status="running", events=events)
    )
    _atomic_write_json(record_path, record)
    _atomic_write_json(metadata_path, metadata)
    return resolution


def stop_run(
    evidence_directory: Path,
    workspace: Path,
    *,
    reason: str,
    detail: str | None = None,
    completion_statement: str | None = None,
    now: Callable[[], datetime] = _utc_now,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> dict[str, Any]:
    evidence_directory = evidence_directory.resolve()
    workspace = workspace.resolve()
    _assert_existing_record_valid(evidence_directory, workspace)
    metadata_path, metadata = _load_native_metadata(evidence_directory)
    record_path = evidence_directory / RECORD_RELATIVE_PATH
    journal_path = evidence_directory / JOURNAL_RELATIVE_PATH
    record = load_json(record_path)
    if record.get("record_state") != "running" or metadata.get("lifecycle_state") != "running":
        raise NativeRunRecorderError("Run can stop exactly once from running state")
    if reason not in STOP_REASONS:
        raise NativeRunRecorderError(f"Unsupported native stop reason: {reason}")
    statement = completion_statement.strip() if isinstance(completion_statement, str) else None
    if reason == "submitted" and not statement:
        raise NativeRunRecorderError("submitted requires the visible completion statement")
    if reason != "submitted" and statement:
        raise NativeRunRecorderError(
            "A non-submitted run cannot carry a completion statement"
        )
    ended_at = _utc_text(now())
    mono_end = monotonic_ns()
    mono_start = record["timing"]["monotonic_start_ns"]
    if not isinstance(mono_start, int) or mono_end < mono_start:
        raise NativeRunRecorderError("Monotonic clock moved backwards or start is missing")
    wall_start = datetime.fromisoformat(record["timing"]["started_at"].replace("Z", "+00:00"))
    wall_end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    wall_elapsed = (wall_end - wall_start).total_seconds()
    if wall_elapsed < 0:
        raise NativeRunRecorderError("UTC wall clock moved backwards during the run")
    elapsed = (mono_end - mono_start) / 1_000_000_000
    signal = "native_visible_completion" if reason == "submitted" else None
    head, _ = inspect_start_commit(workspace)
    fixture_manifest = load_json(
        TASKS_ROOT / metadata["task"]["task_id"] / "fixture_manifest.json"
    )
    final_hash = repository_hash(workspace, fixture_manifest)
    record["record_state"] = "frozen"
    record["workspace"]["final_head"] = head
    record["workspace"]["final_workspace_sha256"] = final_hash
    record["timing"].update(
        {
            "ended_at": ended_at,
            "monotonic_end_ns": mono_end,
            "elapsed_seconds": elapsed,
            "wall_elapsed_seconds": wall_elapsed,
            "wall_minus_monotonic_seconds": wall_elapsed - elapsed,
            "final_state_frozen_at": ended_at,
        }
    )
    record["stopping"] = {
        "reason": reason,
        "detail": detail,
        "visible_completion_statement": statement,
        "submission_signal": signal,
    }
    record["record_sha256"] = _object_sha256(record, "record_sha256")
    if reason == "submitted":
        metadata["lifecycle_state"] = "submitted"
    elif reason == "infrastructure_failure":
        metadata["lifecycle_state"] = "invalidated"
        metadata["validity_status"] = "invalid"
    else:
        metadata["lifecycle_state"] = "suspended"
    metadata["timing"] = {
        "started_at": record["timing"]["started_at"],
        "ended_at": ended_at,
        "elapsed_seconds": elapsed,
    }
    metadata["stopping"] = {
        "reason": reason,
        "detail": detail,
        "submission_signal": signal,
        "submit_marker_seen": False,
    }
    event_type = {
        "submitted": "visible_completion",
        "task_wall_clock_limit": "task_wall_clock_limit",
        "infrastructure_failure": "infrastructure_failure",
    }[reason]
    _append_event(
        journal_path,
        event_type=event_type,
        run_id=metadata["run_id"],
        recorded_at=ended_at,
        monotonic_ns=mono_end,
        details={
            "record_state": "frozen",
            "reason": reason,
            "elapsed_seconds": elapsed,
            "final_workspace_sha256": final_hash,
        },
    )
    clarification_path = evidence_directory / metadata["artifacts"]["clarification_log"]
    clarification_log = load_json(clarification_path)
    clarification_events = clarification_log.get("events")
    if not isinstance(clarification_events, list):
        raise NativeRunRecorderError("clarification_log.json events must be a list")
    _atomic_write_json(
        clarification_path,
        _clarification_log_value(
            metadata, status="completed", events=clarification_events
        ),
    )
    _atomic_write_json(record_path, record)
    _atomic_write_json(metadata_path, metadata)
    return record


def validate_record(evidence_directory: Path, workspace: Path | None = None) -> list[str]:
    evidence_directory = evidence_directory.resolve()
    issues: list[str] = []
    for relative_path in (
        RECORD_RELATIVE_PATH,
        JOURNAL_RELATIVE_PATH,
        PERMISSION_RELATIVE_PATH,
        CLARIFICATION_RELATIVE_PATH,
    ):
        if not (evidence_directory / relative_path).is_file():
            issues.append(f"required native evidence file is missing: {relative_path.as_posix()}")
    if issues:
        return issues
    try:
        _, metadata = _load_native_metadata(evidence_directory)
        record = load_json(evidence_directory / RECORD_RELATIVE_PATH)
        events = _read_journal(evidence_directory / JOURNAL_RELATIVE_PATH)
        permission_events = _read_journal(
            evidence_directory / PERMISSION_RELATIVE_PATH
        )
        clarification_events = _read_journal(
            evidence_directory / CLARIFICATION_RELATIVE_PATH
        )
        clarification_log = load_json(
            evidence_directory / metadata["artifacts"]["clarification_log"]
        )
    except (OSError, ValueError, KeyError, NativeRunRecorderError) as error:
        return [str(error)]
    if record.get("schema_version") != "1.0.0" or record.get("record_type") != "native_ide_run":
        issues.append("native run record header is invalid")
    if record.get("record_state") not in RECORD_STATES:
        issues.append("native run record_state is invalid")
    if record.get("run_id") != metadata.get("run_id"):
        issues.append("native run record run_id does not match metadata")
    expected_artifacts = {
        "task_prompt": metadata["artifacts"]["task_prompt"],
        "transcript": metadata["artifacts"]["transcript"],
        "timing_journal": JOURNAL_RELATIVE_PATH.as_posix(),
        "permission_journal": PERMISSION_RELATIVE_PATH.as_posix(),
        "clarification_journal": CLARIFICATION_RELATIVE_PATH.as_posix(),
        "clarification_log": metadata["artifacts"]["clarification_log"],
    }
    if record.get("artifacts") != expected_artifacts:
        issues.append("native artifact inventory does not match the recorder contract")
    if record.get("record_sha256") != _object_sha256(record, "record_sha256"):
        issues.append("native run record hash mismatch")
    _validate_chain(events, "timing journal", issues)
    _validate_chain(permission_events, "permission journal", issues)
    _validate_chain(clarification_events, "clarification journal", issues)
    expected_events = {"prepared": 1, "running": 2, "frozen": 3}
    if len(events) != expected_events.get(record.get("record_state"), -1):
        issues.append("timing journal length does not match record state")
    heads = record.get("evidence_chain_heads")
    if not isinstance(heads, dict):
        issues.append("native record evidence_chain_heads is missing")
    else:
        expected_heads = {
            "permission_event_sha256": (
                permission_events[-1].get("event_sha256") if permission_events else None
            ),
            "clarification_event_sha256": (
                clarification_events[-1].get("event_sha256")
                if clarification_events
                else None
            ),
        }
        if heads != expected_heads:
            issues.append("native evidence chain heads do not match journals")
    for event in permission_events:
        details = event.get("details")
        if event.get("event_type") != "permission_decision" or not isinstance(details, dict):
            issues.append("permission journal contains an invalid event")
            continue
        if details.get("permission_type") not in PERMISSION_TYPES:
            issues.append("permission event type is invalid")
        if details.get("decision") not in PERMISSION_DECISIONS:
            issues.append("permission event decision is invalid")
        if details.get("scope") not in PERMISSION_SCOPES:
            issues.append("permission event scope is invalid")
        if details.get("information_provided") is not False or details.get(
            "counts_as_clarification"
        ) is not False:
            issues.append("permission event must not provide information or count as clarification")
    authorized = 0
    responses = 0
    for sequence, event in enumerate(clarification_events, 1):
        details = event.get("details")
        if (
            event.get("event_type") != "clarification_request_resolved"
            or not isinstance(details, dict)
        ):
            issues.append("clarification journal contains an invalid event")
            continue
        if details.get("sequence") != sequence:
            issues.append("clarification request sequence is not contiguous")
        authorized += details.get("authorized") is True
        responses += details.get("response_issued") is True
    expected_counts = metadata["clarification"]
    if len(clarification_events) != expected_counts["requests"]:
        issues.append("native clarification request count does not match metadata")
    if authorized != expected_counts["authorized_requests"]:
        issues.append("native authorized clarification count does not match metadata")
    if responses != expected_counts["responses"]:
        issues.append("native clarification response count does not match metadata")
    log_events = clarification_log.get("events")
    if not isinstance(log_events, list):
        issues.append("native clarification_log.json events must be a list")
    else:
        if sum(event.get("event_type") == "request" for event in log_events if isinstance(event, dict)) != expected_counts["requests"]:
            issues.append("canonical clarification request count does not match metadata")
        if sum(event.get("event_type") == "decision" and event.get("authorized") is True for event in log_events if isinstance(event, dict)) != expected_counts["authorized_requests"]:
            issues.append("canonical authorized clarification count does not match metadata")
        if sum(event.get("event_type") == "response" for event in log_events if isinstance(event, dict)) != expected_counts["responses"]:
            issues.append("canonical clarification response count does not match metadata")
        for event in clarification_events:
            details = event.get("details", {})
            detail_sequence = details.get("sequence")
            call_id = (
                f"native-clarification-{detail_sequence:02d}"
                if isinstance(detail_sequence, int)
                and not isinstance(detail_sequence, bool)
                else ""
            )
            request_matches = [
                item
                for item in log_events
                if isinstance(item, dict)
                and item.get("event_type") == "request"
                and item.get("call_id") == call_id
            ]
            decision_matches = [
                item
                for item in log_events
                if isinstance(item, dict)
                and item.get("event_type") == "decision"
                and item.get("call_id") == call_id
            ]
            if len(request_matches) != 1 or request_matches[0].get(
                "request_text"
            ) != details.get("request_text"):
                issues.append("canonical clarification request disagrees with native journal")
            if (
                len(decision_matches) != 1
                or decision_matches[0].get("authorized")
                != details.get("authorized")
                or decision_matches[0].get("reason_code")
                != details.get("reason_code")
            ):
                issues.append("canonical clarification decision disagrees with native journal")
            response_matches = [
                item
                for item in log_events
                if isinstance(item, dict)
                and item.get("event_type") == "response"
                and item.get("call_id") == call_id
            ]
            expected_response_count = 1 if details.get("response_issued") is True else 0
            if len(response_matches) != expected_response_count:
                issues.append("canonical clarification response disagrees with native journal")
            elif response_matches and response_matches[0].get(
                "response_card_id"
            ) != details.get("response_card_id"):
                issues.append("canonical clarification response card disagrees with native journal")
    state_map = {"prepared": "prepared", "running": "running", "frozen": None}
    record_state = record.get("record_state")
    expected_log_status = {
        "prepared": "not_started",
        "running": "running",
        "frozen": "completed",
    }.get(record_state)
    if clarification_log.get("status") != expected_log_status:
        issues.append("clarification log status does not match native record state")
    if record_state != "prepared" and (
        clarification_log.get("run_id") != metadata["run_id"]
        or clarification_log.get("task_id") != metadata["task"]["task_id"]
        or clarification_log.get("clarification_opportunity")
        != metadata["clarification"]["opportunity"]
    ):
        issues.append("clarification log identity does not match metadata")
    if record_state in {"prepared", "running"} and metadata.get("lifecycle_state") != state_map[record_state]:
        issues.append("native run state does not match shared metadata")
    if record_state == "frozen":
        if record["stopping"]["reason"] == "submitted":
            allowed_lifecycle = {
                "submitted",
                "successful",
                "unsuccessful",
                "invalidated",
            }
        elif record["stopping"]["reason"] == "infrastructure_failure":
            allowed_lifecycle = {"invalidated"}
        else:
            allowed_lifecycle = {"suspended", "unsuccessful", "invalidated"}
        if metadata.get("lifecycle_state") not in allowed_lifecycle:
            issues.append("frozen native record does not match shared lifecycle")
        for field in ("started_at", "ended_at", "elapsed_seconds"):
            if metadata["timing"].get(field) != record["timing"].get(field):
                issues.append(f"native timing {field} does not match shared metadata")
        if (
            metadata.get("lifecycle_state") != "invalidated"
            and metadata["stopping"].get("submission_signal")
            != record["stopping"].get("submission_signal")
        ):
            issues.append("native submission signal does not match shared metadata")
    if workspace is not None and record_state == "prepared":
        try:
            head, clean = inspect_start_commit(workspace.resolve())
            if head != record["workspace"]["start_commit"] or not clean:
                issues.append("prepared native workspace is not at its clean start state")
        except (OSError, RuntimeError) as error:
            issues.append(f"cannot inspect native workspace: {error}")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Record and validate a native IDE run.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    for command in (prepare,):
        command.add_argument("evidence", type=Path)
        command.add_argument("workspace", type=Path)
    prepare.add_argument("--native-freeze-id", required=True)
    prepare.add_argument("--product-version", required=True)
    prepare.add_argument("--displayed-model-or-mode", required=True)
    prepare.add_argument("--configuration-sha256", required=True)
    prepare.add_argument("--order-position", type=int, required=True)
    prepare.add_argument("--random-seed", required=True)
    prepare.add_argument("--task-wall-clock-seconds", type=int, required=True)
    prepare.add_argument("--profile-name", default="TSB Evaluation")
    start = subparsers.add_parser("start")
    start.add_argument("evidence", type=Path)
    start.add_argument("workspace", type=Path)
    permission = subparsers.add_parser("permission")
    permission.add_argument("evidence", type=Path)
    permission.add_argument("--prompt-text", required=True)
    permission.add_argument("--permission-type", choices=sorted(PERMISSION_TYPES), required=True)
    permission.add_argument("--decision", choices=sorted(PERMISSION_DECISIONS), required=True)
    permission.add_argument("--scope", choices=sorted(PERMISSION_SCOPES), required=True)
    clarify = subparsers.add_parser("clarify")
    clarify.add_argument("evidence", type=Path)
    clarify.add_argument("--request-text", required=True)
    stop = subparsers.add_parser("stop")
    stop.add_argument("evidence", type=Path)
    stop.add_argument("workspace", type=Path)
    stop.add_argument("--reason", choices=sorted(STOP_REASONS), required=True)
    stop.add_argument("--detail")
    stop.add_argument("--completion-statement")
    validate = subparsers.add_parser("validate")
    validate.add_argument("evidence", type=Path)
    validate.add_argument("--workspace", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "prepare":
        record = prepare_record(
            arguments.evidence,
            arguments.workspace,
            native_freeze_id=arguments.native_freeze_id,
            product_version=arguments.product_version,
            displayed_model_or_mode=arguments.displayed_model_or_mode,
            configuration_sha256=arguments.configuration_sha256,
            order_position=arguments.order_position,
            random_seed=arguments.random_seed,
            task_wall_clock_seconds=arguments.task_wall_clock_seconds,
            profile_name=arguments.profile_name,
        )
        print(f"prepared={record['run_id']}")
    elif arguments.command == "start":
        record = start_run(arguments.evidence, arguments.workspace)
        print(f"started_at={record['timing']['started_at']}")
    elif arguments.command == "permission":
        event = record_permission_event(
            arguments.evidence,
            prompt_text=arguments.prompt_text,
            permission_type=arguments.permission_type,
            decision=arguments.decision,
            scope=arguments.scope,
        )
        print(f"permission_event_sha256={event['event_sha256']}")
    elif arguments.command == "clarify":
        resolution = record_clarification_request(
            arguments.evidence,
            request_text=arguments.request_text,
        )
        print(f"authorized={str(resolution.authorized).lower()}")
        print(f"response_issued={str(resolution.response_issued).lower()}")
        print(f"reason_code={resolution.reason_code}")
        print(f"response_text={resolution.response_text}")
    elif arguments.command == "stop":
        record = stop_run(
            arguments.evidence,
            arguments.workspace,
            reason=arguments.reason,
            detail=arguments.detail,
            completion_statement=arguments.completion_statement,
        )
        print(f"elapsed_seconds={record['timing']['elapsed_seconds']}")
    else:
        issues = validate_record(arguments.evidence, arguments.workspace)
        if issues:
            for issue in issues:
                print(f"ERROR: {issue}")
            raise SystemExit(1)
        print("Native IDE run record is valid.")


if __name__ == "__main__":
    main()
