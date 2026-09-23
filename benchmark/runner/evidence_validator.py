from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .common import (
        ARTIFACT_PATHS,
        BANNED_WORKSPACE_NAMES,
        REPOSITORY_ROOT,
        SYSTEM_PROFILES,
        TASKS_ROOT,
        build_run_id,
        load_json,
        repository_hash,
        sha256_bytes,
    )
    from .git_start_state import inspect_start_commit, start_commit_exists
    from .native_ide_run_recorder import validate_record as validate_native_record
    from .workspace_artifacts import (
        INVENTORY_NAME,
        POLICY_SNAPSHOT_NAME,
        WorkspaceArtifactPolicyError,
        load_policy,
        validate_hash_exclusion_alignment,
        validate_inventory,
    )
except ImportError:  # Supports direct script execution.
    from common import (  # type: ignore
        ARTIFACT_PATHS,
        BANNED_WORKSPACE_NAMES,
        REPOSITORY_ROOT,
        SYSTEM_PROFILES,
        TASKS_ROOT,
        build_run_id,
        load_json,
        repository_hash,
        sha256_bytes,
    )
    from git_start_state import inspect_start_commit, start_commit_exists  # type: ignore
    from native_ide_run_recorder import validate_record as validate_native_record  # type: ignore
    from workspace_artifacts import (  # type: ignore
        INVENTORY_NAME,
        POLICY_SNAPSHOT_NAME,
        WorkspaceArtifactPolicyError,
        load_policy,
        validate_hash_exclusion_alignment,
        validate_inventory,
    )


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
TASK_ID_PATTERN = re.compile(r"^L([1-4])-[0-9]{2}$")
FINAL_STATES = {"successful", "unsuccessful", "invalidated"}
LIMIT_REASONS = {
    "task_wall_clock_limit",
    "api_action_limit",
    "command_timeout",
    "protocol_no_progress_limit",
}
INVALID_REASONS = {
    "evaluator_error",
    "infrastructure_failure",
    "runner_error",
}

TOP_LEVEL_KEYS = {
    "schema_version",
    "run_id",
    "phase",
    "lifecycle_state",
    "validity_status",
    "task",
    "system",
    "schedule",
    "timing",
    "limits",
    "stopping",
    "results",
    "clarification",
    "usage",
    "artifacts",
}
NESTED_KEYS = {
    "task": {
        "task_id",
        "tier",
        "repetition",
        "attempt",
        "fixture_sha256",
        "prompt_sha256",
        "start_commit",
        "clarification_opportunity",
    },
    "system": {
        "system_id",
        "system_slug",
        "evaluation_interface",
        "product_version",
        "model_identifier",
        "provider_endpoint",
        "configuration_sha256",
    },
    "schedule": {"order_position", "random_seed"},
    "timing": {"started_at", "ended_at", "elapsed_seconds"},
    "limits": {
        "task_wall_clock_seconds",
        "api_action_limit",
        "command_timeout_seconds",
        "consecutive_no_action_response_limit",
    },
    "stopping": {"reason", "detail", "submission_signal", "submit_marker_seen"},
    "results": {
        "success",
        "functional_tests",
        "architecture_checks",
        "robustness_eligible",
        "autonomous_success",
    },
    "clarification": {
        "opportunity",
        "requests",
        "authorized_requests",
        "responses",
    },
    "usage": {
        "status",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "monetary_cost",
        "currency",
    },
}
DIAGNOSTIC_KEYS = {"passed", "applicable", "proportion"}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_exact_keys(
    value: Any,
    expected: set[str],
    label: str,
    issues: list[str],
) -> bool:
    if not isinstance(value, dict):
        issues.append(f"{label} must be a JSON object")
        return False
    observed = set(value)
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    if missing:
        issues.append(f"{label} is missing fields: {', '.join(missing)}")
    if extra:
        issues.append(f"{label} has unknown fields: {', '.join(extra)}")
    return not missing and not extra


def _check_nullable_string(value: Any, label: str, issues: list[str]) -> None:
    if value is not None and not isinstance(value, str):
        issues.append(f"{label} must be a string or null")


def _check_nullable_positive_int(value: Any, label: str, issues: list[str]) -> None:
    if value is not None and (not _is_int(value) or value < 1):
        issues.append(f"{label} must be a positive integer or null")


def _check_datetime(value: Any, label: str, issues: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        issues.append(f"{label} must be an RFC 3339 string or null")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        issues.append(f"{label} is not a valid RFC 3339 date-time")
        return
    if parsed.tzinfo is None:
        issues.append(f"{label} must include an explicit timezone")


def _check_diagnostic(value: Any, label: str, issues: list[str]) -> None:
    if not _require_exact_keys(value, DIAGNOSTIC_KEYS, label, issues):
        return
    passed = value["passed"]
    applicable = value["applicable"]
    proportion = value["proportion"]
    for field, observed in (("passed", passed), ("applicable", applicable)):
        if observed is not None and (not _is_int(observed) or observed < 0):
            issues.append(f"{label}.{field} must be a non-negative integer or null")
    if proportion is not None and (
        not _is_number(proportion) or not 0 <= proportion <= 1
    ):
        issues.append(f"{label}.proportion must be between 0 and 1 or null")
    values = (passed, applicable, proportion)
    if any(item is None for item in values) and not all(item is None for item in values):
        issues.append(f"{label} counts and proportion must be populated together")
        return
    if all(item is not None for item in values):
        if passed > applicable:
            issues.append(f"{label}.passed cannot exceed applicable")
        expected = 0.0 if applicable == 0 else passed / applicable
        if not math.isclose(proportion, expected, rel_tol=0, abs_tol=1e-9):
            issues.append(
                f"{label}.proportion must equal passed/applicable ({expected})"
            )


def _validate_metadata_shape(metadata: Any, issues: list[str]) -> None:
    if not _require_exact_keys(metadata, TOP_LEVEL_KEYS, "metadata", issues):
        return
    for field, expected in NESTED_KEYS.items():
        if field == "limits":
            legacy = expected - {"consecutive_no_action_response_limit"}
            observed = metadata[field]
            if not isinstance(observed, dict) or frozenset(observed) not in {
                frozenset(legacy),
                frozenset(expected),
            }:
                _require_exact_keys(observed, expected, field, issues)
            continue
        _require_exact_keys(metadata[field], expected, field, issues)
    if isinstance(metadata.get("results"), dict):
        _check_diagnostic(
            metadata["results"].get("functional_tests"),
            "results.functional_tests",
            issues,
        )
        _check_diagnostic(
            metadata["results"].get("architecture_checks"),
            "results.architecture_checks",
            issues,
        )
    _require_exact_keys(metadata.get("artifacts"), set(ARTIFACT_PATHS), "artifacts", issues)


def _validate_metadata_values(metadata: dict[str, Any], issues: list[str]) -> None:
    if metadata.get("schema_version") != "1.0.0":
        issues.append("schema_version must be 1.0.0")
    phase = metadata.get("phase")
    if phase not in {"validation", "pilot", "main"}:
        issues.append("phase must be validation, pilot, or main")
    state = metadata.get("lifecycle_state")
    if state not in {
        "prepared",
        "running",
        "submitted",
        "suspended",
        "evaluating",
        "successful",
        "unsuccessful",
        "invalidated",
    }:
        issues.append("lifecycle_state is not recognized")
    validity = metadata.get("validity_status")
    if validity not in {"pending", "valid", "invalid"}:
        issues.append("validity_status must be pending, valid, or invalid")

    task = metadata.get("task", {})
    system = metadata.get("system", {})
    schedule = metadata.get("schedule", {})
    timing = metadata.get("timing", {})
    limits = metadata.get("limits", {})
    stopping = metadata.get("stopping", {})
    results = metadata.get("results", {})
    clarification = metadata.get("clarification", {})
    usage = metadata.get("usage", {})

    task_id = task.get("task_id")
    match = TASK_ID_PATTERN.fullmatch(task_id) if isinstance(task_id, str) else None
    if not match:
        issues.append("task.task_id must match L<tier>-<two digits>")
    tier = task.get("tier")
    if not _is_int(tier) or not 1 <= tier <= 4:
        issues.append("task.tier must be an integer from 1 to 4")
    elif match and int(match.group(1)) != tier:
        issues.append("task.tier does not match task.task_id")
    for field in ("repetition", "attempt"):
        value = task.get(field)
        if not _is_int(value) or not 1 <= value <= 99:
            issues.append(f"task.{field} must be an integer from 1 to 99")
    for field in ("fixture_sha256", "prompt_sha256"):
        value = task.get(field)
        if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            issues.append(f"task.{field} must be a lowercase SHA-256 digest")
    start_commit = task.get("start_commit")
    if not isinstance(start_commit, str) or not re.fullmatch(r"[a-f0-9]{40}", start_commit):
        issues.append("task.start_commit must be a full 40-character Git commit")
    if not isinstance(task.get("clarification_opportunity"), bool):
        issues.append("task.clarification_opportunity must be boolean")

    system_id = system.get("system_id")
    if system_id not in SYSTEM_PROFILES:
        issues.append("system.system_id is not recognized")
    else:
        expected_slug, expected_interface = SYSTEM_PROFILES[system_id]
        if system.get("system_slug") != expected_slug:
            issues.append("system.system_slug does not match system.system_id")
        if system.get("evaluation_interface") != expected_interface:
            issues.append("system.evaluation_interface does not match system.system_id")
    for field in ("product_version", "model_identifier", "provider_endpoint"):
        _check_nullable_string(system.get(field), f"system.{field}", issues)
    configuration_hash = system.get("configuration_sha256")
    if configuration_hash is not None and (
        not isinstance(configuration_hash, str)
        or not SHA256_PATTERN.fullmatch(configuration_hash)
    ):
        issues.append("system.configuration_sha256 must be a SHA-256 digest or null")

    if (
        isinstance(phase, str)
        and isinstance(task_id, str)
        and system_id in SYSTEM_PROFILES
        and _is_int(task.get("repetition"))
        and _is_int(task.get("attempt"))
    ):
        expected_run_id = build_run_id(
            phase,
            task_id,
            SYSTEM_PROFILES[system_id][0],
            task["repetition"],
            task["attempt"],
        )
        if metadata.get("run_id") != expected_run_id:
            issues.append(f"run_id must be {expected_run_id}")

    order_position = schedule.get("order_position")
    if order_position is not None and (
        not _is_int(order_position) or not 1 <= order_position <= 4
    ):
        issues.append("schedule.order_position must be 1 through 4 or null")
    _check_nullable_string(schedule.get("random_seed"), "schedule.random_seed", issues)

    for field in ("started_at", "ended_at"):
        _check_datetime(timing.get(field), f"timing.{field}", issues)
    elapsed = timing.get("elapsed_seconds")
    if elapsed is not None and (not _is_number(elapsed) or elapsed < 0):
        issues.append("timing.elapsed_seconds must be non-negative or null")
    for field in (
        "task_wall_clock_seconds",
        "api_action_limit",
        "command_timeout_seconds",
        "consecutive_no_action_response_limit",
    ):
        _check_nullable_positive_int(limits.get(field), f"limits.{field}", issues)

    reason = stopping.get("reason")
    allowed_reasons = {None, "submitted", *LIMIT_REASONS, *INVALID_REASONS}
    if reason not in allowed_reasons:
        issues.append("stopping.reason is not recognized")
    _check_nullable_string(stopping.get("detail"), "stopping.detail", issues)
    submission_signal = stopping.get("submission_signal")
    if submission_signal not in {
        None,
        "api_submit_marker",
        "native_visible_completion",
    }:
        issues.append("stopping.submission_signal is not recognized")
    if not isinstance(stopping.get("submit_marker_seen"), bool):
        issues.append("stopping.submit_marker_seen must be boolean")
    if stopping.get("submit_marker_seen") != (
        submission_signal == "api_submit_marker"
    ):
        issues.append("submit_marker_seen must be true exactly for api_submit_marker")
    if submission_signal is not None and reason != "submitted":
        issues.append("submission_signal requires stopping.reason submitted")

    success = results.get("success")
    if success is not None and not isinstance(success, bool):
        issues.append("results.success must be boolean or null")
    expected_robustness = phase in {"pilot", "main"} and tier in {3, 4}
    if results.get("robustness_eligible") != expected_robustness:
        issues.append("results.robustness_eligible is inconsistent with phase/tier")
    autonomous = results.get("autonomous_success")
    if autonomous is not None and not isinstance(autonomous, bool):
        issues.append("results.autonomous_success must be boolean or null")

    for field in ("requests", "authorized_requests", "responses"):
        value = clarification.get(field)
        if not _is_int(value) or value < 0:
            issues.append(f"clarification.{field} must be a non-negative integer")
    if clarification.get("opportunity") != task.get("clarification_opportunity"):
        issues.append("clarification.opportunity must match the task specification")
    requests = clarification.get("requests")
    authorized = clarification.get("authorized_requests")
    responses = clarification.get("responses")
    if all(_is_int(value) for value in (requests, authorized, responses)):
        if not responses <= authorized <= requests:
            issues.append("clarification counts must satisfy responses <= authorized <= requests")
        if not clarification.get("opportunity") and (authorized or responses):
            issues.append("complete-brief runs cannot have authorized requests or responses")

    usage_status = usage.get("status")
    if usage_status not in {"available", "unavailable", "not_applicable"}:
        issues.append("usage.status is not recognized")
    usage_values = (
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        usage.get("total_tokens"),
        usage.get("monetary_cost"),
        usage.get("currency"),
    )
    if usage_status != "available" and any(value is not None for value in usage_values):
        issues.append("unavailable/not-applicable usage values must be null")
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        value = usage.get(field)
        if value is not None and (not _is_int(value) or value < 0):
            issues.append(f"usage.{field} must be a non-negative integer or null")
    cost = usage.get("monetary_cost")
    if cost is not None and (not _is_number(cost) or cost < 0):
        issues.append("usage.monetary_cost must be non-negative or null")
    currency = usage.get("currency")
    if currency is not None and (
        not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)
    ):
        issues.append("usage.currency must be a three-letter uppercase code or null")
    if usage_status == "available":
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")
        if all(_is_int(value) for value in (input_tokens, output_tokens, total_tokens)):
            if input_tokens + output_tokens != total_tokens:
                issues.append("usage.total_tokens must equal input_tokens + output_tokens")

    interface = system.get("evaluation_interface")
    if interface == "api_wrapper":
        expected_signal = "api_submit_marker" if reason == "submitted" else None
        if submission_signal != expected_signal:
            issues.append("API-wrapper submission_signal does not match stopping.reason")
    elif interface == "native_ide":
        expected_signal = "native_visible_completion" if reason == "submitted" else None
        if submission_signal != expected_signal:
            issues.append("native-IDE submission_signal does not match stopping.reason")
    elif submission_signal is not None:
        issues.append("researcher validation cannot record an agent submission_signal")
    if interface != "api_wrapper" and (
        limits.get("api_action_limit") is not None
        or limits.get("command_timeout_seconds") is not None
        or limits.get("consecutive_no_action_response_limit") is not None
    ):
        issues.append("API-specific limits must be null outside the API wrapper")
    if interface == "api_wrapper" and (
        limits.get("api_action_limit") is None
        or limits.get("command_timeout_seconds") is None
        or (
            "consecutive_no_action_response_limit" in limits
            and limits.get("consecutive_no_action_response_limit") is None
        )
    ):
        issues.append(
            "API-wrapper runs require action, command-timeout, and consecutive no-action limits"
        )
    if interface == "researcher_validation" and usage_status != "not_applicable":
        issues.append("researcher validation usage must be not_applicable")
    if phase in {"pilot", "main"} and system_id in {"baseline", "oracle"}:
        issues.append("baseline/oracle actors are validation-only")
    if phase == "main" and task.get("repetition") not in {1, 2, 3}:
        issues.append("main runs must use repetition 1, 2, or 3")

    _validate_lifecycle(metadata, issues)


def _validate_lifecycle(metadata: dict[str, Any], issues: list[str]) -> None:
    state = metadata["lifecycle_state"]
    validity = metadata["validity_status"]
    timing = metadata["timing"]
    stopping = metadata["stopping"]
    results = metadata["results"]
    phase = metadata["phase"]
    system = metadata["system"]
    task = metadata["task"]
    schedule = metadata["schedule"]

    if state in {"prepared", "running", "submitted", "suspended", "evaluating"}:
        if validity != "pending":
            issues.append(f"{state} runs must have pending validity")
        if results["success"] is not None:
            issues.append(f"{state} runs cannot have a final success value")
    if state == "prepared":
        if any(timing[field] is not None for field in timing):
            issues.append("prepared runs cannot have timing values")
        if stopping["reason"] is not None:
            issues.append("prepared runs cannot have a stopping reason")
    if state == "running":
        if timing["started_at"] is None or timing["ended_at"] is not None:
            issues.append("running runs require started_at and no ended_at")
    if state in {"submitted", "suspended", "evaluating", *FINAL_STATES}:
        if (
            timing["started_at"] is None
            or timing["ended_at"] is None
            or timing["elapsed_seconds"] is None
        ):
            issues.append(f"{state} runs require complete timing values")
        if stopping["reason"] is None:
            issues.append(f"{state} runs require a stopping reason")
    if state == "submitted" and stopping["reason"] != "submitted":
        issues.append("submitted state requires submitted stopping reason")
    if state == "suspended" and stopping["reason"] not in LIMIT_REASONS:
        issues.append("suspended state requires a limit stopping reason")
    if state == "successful":
        if validity != "valid" or results["success"] is not True:
            issues.append("successful runs require valid=true primary outcome")
        if stopping["reason"] != "submitted":
            issues.append("successful runs must end by submission")
        for label in ("functional_tests", "architecture_checks"):
            diagnostic = results[label]
            if diagnostic.get("proportion") != 1:
                issues.append(f"successful runs require results.{label}.proportion=1")
    if state == "unsuccessful":
        if validity != "valid" or results["success"] is not False:
            issues.append("unsuccessful runs require valid=false primary outcome")
        if stopping["reason"] not in {"submitted", *LIMIT_REASONS}:
            issues.append("unsuccessful runs require submission or a limit reason")
    if state == "invalidated":
        if validity != "invalid" or results["success"] is not None:
            issues.append("invalidated runs require invalid validity and null success")
        if stopping["reason"] not in INVALID_REASONS:
            issues.append("invalidated runs require a formal invalidation reason")
    if stopping["reason"] in LIMIT_REASONS and state == "successful":
        issues.append("limit-stopped runs cannot be successful")

    if state in FINAL_STATES and state != "invalidated":
        for label in ("functional_tests", "architecture_checks"):
            if any(value is None for value in results[label].values()):
                issues.append(f"final valid runs require complete {label} diagnostics")
    if results["robustness_eligible"]:
        autonomous = results["autonomous_success"]
        if state in {"successful", "unsuccessful"} and autonomous is None:
            issues.append("final robustness-eligible runs require autonomous_success")
        if autonomous is True and (
            results["success"] is not True or metadata["clarification"]["responses"] != 0
        ):
            issues.append("autonomous_success requires success without an evaluator response")
    elif results["autonomous_success"] is not None:
        issues.append("non-eligible runs must use null autonomous_success")

    if state != "prepared" and phase in {"pilot", "main"}:
        required_freeze_values = {
            "task.start_commit": task["start_commit"],
            "system.configuration_sha256": system["configuration_sha256"],
            "schedule.order_position": schedule["order_position"],
            "schedule.random_seed": schedule["random_seed"],
            "limits.task_wall_clock_seconds": metadata["limits"][
                "task_wall_clock_seconds"
            ],
        }
        for label, value in required_freeze_values.items():
            if value is None:
                issues.append(f"started pilot/main runs require {label}")


def _load_json_artifact(path: Path, issues: list[str]) -> dict[str, Any] | None:
    try:
        return load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        issues.append(f"{path.name} is not a valid JSON object: {error}")
        return None


def _validate_jsonl(path: Path, issues: list[str]) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        issues.append(f"{path.name} cannot be read as UTF-8: {error}")
        return
    records = 0
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        records += 1
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            issues.append(f"{path.name}:{line_number} is invalid JSON: {error.msg}")
            continue
        if not isinstance(value, dict):
            issues.append(f"{path.name}:{line_number} must contain a JSON object")
    if records == 0:
        issues.append(f"{path.name} must contain an availability or evidence record")


def _validate_result_artifact(
    artifact: dict[str, Any] | None,
    metadata_result: dict[str, Any],
    item_key: str,
    artifact_name: str,
    final_run: bool,
    issues: list[str],
) -> None:
    if artifact is None:
        return
    status = artifact.get("status")
    items = artifact.get(item_key)
    if status not in {"not_run", "completed", "error"}:
        issues.append(f"{artifact_name}.status is not recognized")
    if not isinstance(items, list):
        issues.append(f"{artifact_name}.{item_key} must be a list")
        return
    if final_run and status != "completed":
        issues.append(f"final valid runs require completed {artifact_name}")
    if status != "completed":
        return
    applicable = 0
    passed = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            issues.append(f"{artifact_name}.{item_key}[{index}] must be an object")
            continue
        if not isinstance(item.get("id"), str) or not item["id"]:
            issues.append(f"{artifact_name}.{item_key}[{index}].id is required")
        if not isinstance(item.get("applicable"), bool):
            issues.append(
                f"{artifact_name}.{item_key}[{index}].applicable must be boolean"
            )
            continue
        if not isinstance(item.get("passed"), bool):
            issues.append(f"{artifact_name}.{item_key}[{index}].passed must be boolean")
            continue
        if item["applicable"]:
            applicable += 1
            passed += int(item["passed"])
    if metadata_result.get("applicable") != applicable:
        issues.append(f"{artifact_name} applicable count disagrees with metadata")
    if metadata_result.get("passed") != passed:
        issues.append(f"{artifact_name} passed count disagrees with metadata")


def _validate_task_package(
    metadata: dict[str, Any],
    evidence_directory: Path,
    tasks_root: Path,
    issues: list[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    task_id = metadata["task"]["task_id"]
    task_root = tasks_root / task_id
    try:
        task_spec = load_json(task_root / "task_spec.json")
        fixture_manifest = load_json(task_root / "fixture_manifest.json")
        prompt_bytes = (task_root / "public_task_brief.md").read_bytes()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        issues.append(f"Cannot load frozen task package for {task_id}: {error}")
        return None, None
    if task_spec.get("task_id") != task_id or fixture_manifest.get("task_id") != task_id:
        issues.append("Frozen task package has inconsistent task IDs")
    if task_spec.get("tier") != metadata["task"]["tier"]:
        issues.append("metadata task tier disagrees with task_spec.json")
    if bool(task_spec.get("clarification_opportunity")) != metadata["task"][
        "clarification_opportunity"
    ]:
        issues.append("metadata clarification opportunity disagrees with task_spec.json")
    if fixture_manifest.get("aggregate_fixture_hash") != metadata["task"][
        "fixture_sha256"
    ]:
        issues.append("metadata fixture hash disagrees with fixture_manifest.json")
    if fixture_manifest.get("start_commit") != metadata["task"]["start_commit"]:
        issues.append("metadata start commit disagrees with fixture_manifest.json")
    if sha256_bytes(prompt_bytes) != metadata["task"]["prompt_sha256"]:
        issues.append("metadata prompt hash disagrees with the frozen public brief")
    prompt_path = evidence_directory / ARTIFACT_PATHS["task_prompt"]
    try:
        evidence_prompt = prompt_path.read_bytes()
    except OSError as error:
        issues.append(f"Cannot read task_prompt.txt: {error}")
    else:
        if evidence_prompt != prompt_bytes:
            issues.append("task_prompt.txt differs from the frozen public brief")
        if sha256_bytes(evidence_prompt) != metadata["task"]["prompt_sha256"]:
            issues.append("task_prompt.txt hash disagrees with metadata")
    _validate_evaluator_manifest(
        task_root, task_spec, fixture_manifest, metadata, issues
    )
    return task_spec, fixture_manifest


def _validate_evaluator_manifest(
    task_root: Path,
    task_spec: dict[str, Any],
    fixture_manifest: dict[str, Any],
    metadata: dict[str, Any],
    issues: list[str],
) -> None:
    manifest_path = task_root / "evaluator_manifest.json"
    try:
        manifest = load_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        issues.append(f"Cannot load evaluator_manifest.json: {error}")
        return
    expected_keys = {
        "schema_version",
        "task_id",
        "review_status",
        "pytest_environment_variable",
        "functional_tests",
        "architecture_checks",
        "operational_evidence",
    }
    if not _require_exact_keys(manifest, expected_keys, "evaluator_manifest", issues):
        return
    if manifest["schema_version"] != "1.0.0":
        issues.append("evaluator_manifest schema_version must be 1.0.0")
    if manifest["task_id"] != task_spec.get("task_id"):
        issues.append("evaluator_manifest task_id disagrees with task_spec.json")
    if manifest["review_status"] not in {"draft", "approved"}:
        issues.append("evaluator_manifest review_status is not recognized")
    tracking = fixture_manifest.get("evaluator_manifest")
    if not isinstance(tracking, dict):
        issues.append("fixture_manifest.json is missing evaluator_manifest tracking")
    else:
        if tracking.get("path") != "evaluator_manifest.json":
            issues.append("fixture manifest evaluator path is not canonical")
        if tracking.get("review_status") != manifest["review_status"]:
            issues.append("evaluator review status disagrees with fixture_manifest.json")
    environment_variable = manifest["pytest_environment_variable"]
    if environment_variable is not None and not isinstance(environment_variable, str):
        issues.append("evaluator_manifest pytest_environment_variable must be string or null")

    item_keys = {"id", "description", "runner", "source", "implementation_status"}
    architecture_keys = {"id", "requirement", "evidence", "implementation_status"}
    evidence_keys = {"source_id", "source"}
    ids: set[str] = set()
    pending = False
    for group in ("functional_tests", "operational_evidence"):
        items = manifest[group]
        if not isinstance(items, list) or (group == "functional_tests" and not items):
            issues.append(f"evaluator_manifest {group} must be a non-empty list")
            continue
        for index, item in enumerate(items):
            label = f"evaluator_manifest.{group}[{index}]"
            if not _require_exact_keys(item, item_keys, label, issues):
                continue
            item_id = item["id"]
            if not isinstance(item_id, str) or not re.fullmatch(r"[a-z0-9_]+", item_id):
                issues.append(f"{label}.id is invalid")
            elif item_id in ids:
                issues.append(f"Duplicate evaluator item id: {item_id}")
            else:
                ids.add(item_id)
            if item["runner"] not in {"pytest", "node", "compose_probe", "global_validator"}:
                issues.append(f"{label}.runner is not recognized")
            pending |= not _validate_manifest_source(
                task_root, item["source"], item["implementation_status"], label, issues
            )

    architecture = manifest["architecture_checks"]
    requirements: list[str] = []
    if not isinstance(architecture, list) or not architecture:
        issues.append("evaluator_manifest architecture_checks must be a non-empty list")
    else:
        for index, item in enumerate(architecture):
            label = f"evaluator_manifest.architecture_checks[{index}]"
            if not _require_exact_keys(item, architecture_keys, label, issues):
                continue
            item_id = item["id"]
            if not isinstance(item_id, str) or not re.fullmatch(r"[a-z0-9_]+", item_id):
                issues.append(f"{label}.id is invalid")
            elif item_id in ids:
                issues.append(f"Duplicate evaluator item id: {item_id}")
            else:
                ids.add(item_id)
            requirements.append(item["requirement"])
            evidence = item["evidence"]
            if not isinstance(evidence, list) or not evidence:
                issues.append(f"{label}.evidence must be a non-empty list")
            else:
                for evidence_index, reference in enumerate(evidence):
                    reference_label = f"{label}.evidence[{evidence_index}]"
                    if not _require_exact_keys(reference, evidence_keys, reference_label, issues):
                        continue
                    _validate_manifest_source(
                        task_root,
                        reference["source"],
                        item["implementation_status"],
                        reference_label,
                        issues,
                    )
            status = item["implementation_status"]
            if status not in {"implemented", "pending_implementation"}:
                issues.append(f"{label}.implementation_status is not recognized")
            pending |= status == "pending_implementation"

    if requirements != task_spec.get("architectural_invariants"):
        issues.append(
            "evaluator_manifest architecture requirements must exactly match "
            "task_spec.json order and wording"
        )
    if (
        metadata["phase"] in {"pilot", "main"}
        and metadata["lifecycle_state"] != "prepared"
        and (
            manifest["review_status"] != "approved"
            or pending
            or not isinstance(tracking, dict)
            or tracking.get("post_change_full_cycle_revalidation_required") is not False
        )
    ):
        issues.append(
            "started pilot/main runs require an approved evaluator manifest "
            "with no pending checks or required revalidation"
        )


def _validate_manifest_source(
    task_root: Path,
    source: Any,
    status: Any,
    label: str,
    issues: list[str],
) -> bool:
    if status not in {"implemented", "pending_implementation"}:
        issues.append(f"{label}.implementation_status is not recognized")
        return False
    if not isinstance(source, str) or not source:
        issues.append(f"{label}.source must be a non-empty string")
        return status == "implemented"
    path_text = source.split("::", maxsplit=1)[0]
    source_path = (
        REPOSITORY_ROOT / path_text
        if path_text.startswith("benchmark/")
        else task_root / path_text
    )
    if status == "implemented" and not source_path.is_file():
        issues.append(f"{label} implemented source does not exist: {path_text}")
    return status == "implemented"


def _validate_workspace(
    workspace: Path,
    metadata: dict[str, Any],
    fixture_manifest: dict[str, Any] | None,
    issues: list[str],
) -> None:
    if not workspace.is_dir():
        issues.append(f"Workspace does not exist: {workspace}")
        return
    banned_casefold = {name.casefold() for name in BANNED_WORKSPACE_NAMES}
    # Post-run, run-specific validity disposition authorized by the user.
    # These are the four unchanged links created by `python -m venv .venv`;
    # every other symbolic link remains prohibited.
    allowed_links = (
        {
            ".venv/lib64": "lib",
            ".venv/bin/python": "/usr/local/bin/python",
            ".venv/bin/python3": "python",
            ".venv/bin/python3.12": "python",
        }
        if metadata["run_id"] == "main-L3-01-gpt-5-4-r01-a01"
        else {}
    )
    for path in workspace.rglob("*"):
        if path.name.casefold() in banned_casefold:
            issues.append(f"Agent workspace exposes researcher-only path: {path}")
        if path.is_symlink():
            relative = path.relative_to(workspace).as_posix()
            if path.readlink().as_posix() != allowed_links.get(relative):
                issues.append(f"Agent workspace contains a symbolic link: {path}")
    if metadata["lifecycle_state"] == "prepared" and fixture_manifest is not None:
        observed = repository_hash(workspace, fixture_manifest)
        expected = metadata["task"]["fixture_sha256"]
        if observed != expected:
            issues.append(
                f"Prepared workspace hash mismatch: expected {expected}, observed {observed}"
            )
    expected_commit = metadata["task"]["start_commit"]
    if not start_commit_exists(workspace, expected_commit):
        issues.append(f"Workspace does not contain frozen start commit {expected_commit}")
        return
    if metadata["lifecycle_state"] == "prepared":
        try:
            head, clean = inspect_start_commit(workspace)
        except (FileNotFoundError, RuntimeError) as error:
            issues.append(f"Cannot inspect prepared Git workspace: {error}")
            return
        if head != expected_commit:
            issues.append(
                f"Prepared workspace HEAD mismatch: expected {expected_commit}, observed {head}"
            )
        if not clean:
            issues.append("Prepared workspace must be clean")


def _validate_workspace_artifact_evidence(
    evidence_directory: Path,
    metadata: dict[str, Any],
    fixture_manifest: dict[str, Any] | None,
    workspace: Path | None,
    issues: list[str],
) -> None:
    policy_path = evidence_directory / POLICY_SNAPSHOT_NAME
    inventory_path = evidence_directory / INVENTORY_NAME
    if not policy_path.exists() and not inventory_path.exists():
        # Prospective policy: historical frozen runs such as a03 remain valid.
        return
    if not policy_path.is_file() or not inventory_path.is_file():
        issues.append(
            "Workspace artifact policy snapshot and incidental inventory must both exist"
        )
        return
    try:
        policy = load_policy(policy_path)
    except WorkspaceArtifactPolicyError as error:
        issues.append(str(error))
        return
    if fixture_manifest is not None:
        issues.extend(validate_hash_exclusion_alignment(policy, fixture_manifest))
    try:
        inventory = load_json(inventory_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        issues.append(f"incidental_artifacts.json is not valid JSON: {error}")
        return
    lifecycle = metadata["lifecycle_state"]
    require_completed = lifecycle in {"successful", "unsuccessful"} or (
        lifecycle in {"evaluating", "invalidated"}
        and inventory.get("status") == "completed"
    )
    issues.extend(
        validate_inventory(
            inventory,
            policy_path=policy_path,
            policy=policy,
            workspace=workspace,
            require_completed=require_completed,
        )
    )
    if require_completed:
        try:
            final_diff = (evidence_directory / ARTIFACT_PATHS["final_diff"]).read_bytes()
        except OSError as error:
            issues.append(f"Cannot inspect final.diff for incidental artifacts: {error}")
            return
        for entry in inventory.get("entries", []):
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                continue
            marker = (
                f"diff --git a/{entry['path']} b/{entry['path']}".encode(
                    "utf-8", errors="surrogateescape"
                )
            )
            if marker in final_diff:
                issues.append(
                    "final.diff includes inventoried incidental artifact: "
                    + entry["path"]
                )


def validate_run(
    evidence_directory: Path,
    *,
    workspace: Path | None = None,
    tasks_root: Path = TASKS_ROOT,
) -> list[str]:
    evidence_directory = evidence_directory.resolve()
    issues: list[str] = []
    metadata_path = evidence_directory / "metadata.json"
    try:
        metadata = load_json(metadata_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return [f"metadata.json is not a valid JSON object: {error}"]

    _validate_metadata_shape(metadata, issues)
    if issues:
        return issues
    _validate_metadata_values(metadata, issues)
    if evidence_directory.name != metadata["run_id"]:
        issues.append("Evidence directory name must equal metadata.run_id")

    if metadata["artifacts"] != ARTIFACT_PATHS:
        issues.append("artifacts must use the canonical evidence filenames")
    for filename in ARTIFACT_PATHS.values():
        path = evidence_directory / filename
        if not path.is_file():
            issues.append(f"Required evidence file is missing: {filename}")
    if issues and any("missing" in issue for issue in issues):
        return issues

    task_spec, fixture_manifest = _validate_task_package(
        metadata, evidence_directory, tasks_root, issues
    )
    del task_spec

    for key in ("raw_model_response", "adapter_decisions"):
        _validate_jsonl(evidence_directory / ARTIFACT_PATHS[key], issues)
    clarification_log = _load_json_artifact(
        evidence_directory / ARTIFACT_PATHS["clarification_log"], issues
    )
    hidden_results = _load_json_artifact(
        evidence_directory / ARTIFACT_PATHS["hidden_test_results"], issues
    )
    architecture_results = _load_json_artifact(
        evidence_directory / ARTIFACT_PATHS["architecture_checks"], issues
    )
    _load_json_artifact(
        evidence_directory / ARTIFACT_PATHS["database_checks"], issues
    )

    if clarification_log is not None:
        events = clarification_log.get("events")
        if not isinstance(events, list):
            issues.append("clarification_log.json events must be a list")
        elif metadata["lifecycle_state"] in FINAL_STATES:
            requests = sum(
                1
                for event in events
                if isinstance(event, dict) and event.get("event_type") == "request"
            )
            authorized = sum(
                1
                for event in events
                if isinstance(event, dict)
                and event.get("event_type") == "decision"
                and event.get("authorized") is True
            )
            responses = sum(
                1
                for event in events
                if isinstance(event, dict) and event.get("event_type") == "response"
            )
            expected = metadata["clarification"]
            if requests != expected["requests"]:
                issues.append("clarification request count disagrees with clarification_log.json")
            if authorized != expected["authorized_requests"]:
                issues.append("authorized request count disagrees with clarification_log.json")
            if responses != expected["responses"]:
                issues.append("clarification response count disagrees with clarification_log.json")

    final_valid = metadata["lifecycle_state"] in {"successful", "unsuccessful"}
    _validate_result_artifact(
        hidden_results,
        metadata["results"]["functional_tests"],
        "tests",
        "hidden_test_results.json",
        final_valid,
        issues,
    )
    _validate_result_artifact(
        architecture_results,
        metadata["results"]["architecture_checks"],
        "checks",
        "architecture_checks.json",
        final_valid,
        issues,
    )

    if workspace is not None:
        _validate_workspace(workspace.resolve(), metadata, fixture_manifest, issues)
    _validate_workspace_artifact_evidence(
        evidence_directory,
        metadata,
        fixture_manifest,
        workspace.resolve() if workspace is not None else None,
        issues,
    )
    native_record_exists = (evidence_directory / "native_ide" / "run_record.json").is_file()
    if metadata["system"]["evaluation_interface"] == "native_ide" and (
        metadata["lifecycle_state"] != "prepared" or native_record_exists
    ):
        issues.extend(validate_native_record(evidence_directory, workspace))
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a TSB run evidence directory without modifying it."
    )
    parser.add_argument("evidence_directory", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--tasks-root", type=Path, default=TASKS_ROOT)
    arguments = parser.parse_args()
    issues = validate_run(
        arguments.evidence_directory,
        workspace=arguments.workspace,
        tasks_root=arguments.tasks_root,
    )
    if issues:
        print(f"INVALID: {len(issues)} issue(s)")
        for issue in issues:
            print(f"- {issue}")
        raise SystemExit(1)
    print(f"VALID: {arguments.evidence_directory.resolve()}")


if __name__ == "__main__":
    main()
