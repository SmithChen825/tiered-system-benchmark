from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .common import (
        REPOSITORY_ROOT,
        TASKS_ROOT,
        load_json,
        repository_hash,
        write_json,
    )
    from .evidence_validator import validate_run
    from .git_start_state import find_git, start_commit_exists
    from .workspace_artifacts import (
        INVENTORY_NAME,
        POLICY_SNAPSHOT_NAME,
        WorkspaceArtifactPolicyError,
        build_inventory,
        load_policy,
        validate_hash_exclusion_alignment,
    )
except ImportError:  # Supports direct script execution.
    from common import (  # type: ignore
        REPOSITORY_ROOT,
        TASKS_ROOT,
        load_json,
        repository_hash,
        write_json,
    )
    from evidence_validator import validate_run  # type: ignore
    from git_start_state import find_git, start_commit_exists  # type: ignore
    from workspace_artifacts import (  # type: ignore
        INVENTORY_NAME,
        POLICY_SNAPSHOT_NAME,
        WorkspaceArtifactPolicyError,
        build_inventory,
        load_policy,
        validate_hash_exclusion_alignment,
    )


FINALIZER_VERSION = "0.1.0"
LIMIT_REASONS = {
    "task_wall_clock_limit",
    "api_action_limit",
    "command_timeout",
    "protocol_no_progress_limit",
}
VALID_STOP_REASONS = {"submitted", *LIMIT_REASONS}
BUNDLE_KEYS = {
    "schema_version",
    "run_id",
    "task_id",
    "workspace_sha256",
    "evaluator_version",
    "evaluated_at",
    "functional_tests",
    "architecture_checks",
    "operational_evidence",
    "docker_status",
    "docker_logs",
    "database_checks",
    "evaluation_error",
}
CHECK_KEYS = {
    "id",
    "applicable",
    "passed",
    "duration_seconds",
    "detail",
    "evidence",
}
OPERATIONAL_KEYS = {"id", "status", "detail", "evidence"}


class FinalizationError(RuntimeError):
    pass


def _exact_keys(value: Any, expected: set[str], label: str, issues: list[str]) -> bool:
    if not isinstance(value, dict):
        issues.append(f"{label} must be an object")
        return False
    observed = set(value)
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    if missing:
        issues.append(f"{label} is missing: {', '.join(missing)}")
    if extra:
        issues.append(f"{label} has unknown fields: {', '.join(extra)}")
    return not missing and not extra


def _parse_datetime(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise FinalizationError(f"{label} is not a valid RFC 3339 date-time") from error
    if parsed.tzinfo is None:
        raise FinalizationError(f"{label} must include an explicit timezone")
    return parsed


def _validate_check_results(
    value: Any,
    label: str,
    issues: list[str],
) -> list[str]:
    if not isinstance(value, list):
        issues.append(f"{label} must be an array")
        return []
    ids: list[str] = []
    for index, item in enumerate(value):
        item_label = f"{label}[{index}]"
        if not _exact_keys(item, CHECK_KEYS, item_label, issues):
            continue
        item_id = item["id"]
        if not isinstance(item_id, str) or not re.fullmatch(r"[a-z0-9_]+", item_id):
            issues.append(f"{item_label}.id is invalid")
        else:
            ids.append(item_id)
        applicable = item["applicable"]
        passed = item["passed"]
        if not isinstance(applicable, bool):
            issues.append(f"{item_label}.applicable must be boolean")
        elif applicable and not isinstance(passed, bool):
            issues.append(f"{item_label}.passed must be boolean when applicable")
        elif not applicable and passed is not None:
            issues.append(f"{item_label}.passed must be null when not applicable")
        duration = item["duration_seconds"]
        if duration is not None and (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or duration < 0
        ):
            issues.append(f"{item_label}.duration_seconds must be non-negative or null")
        detail = item["detail"]
        if detail is not None and not isinstance(detail, str):
            issues.append(f"{item_label}.detail must be string or null")
        evidence = item["evidence"]
        if not isinstance(evidence, list) or not all(
            isinstance(entry, str) for entry in evidence
        ):
            issues.append(f"{item_label}.evidence must be an array of strings")
    if len(ids) != len(set(ids)):
        issues.append(f"{label} contains duplicate IDs")
    return ids


def _validate_operational_results(value: Any, issues: list[str]) -> list[str]:
    if not isinstance(value, list):
        issues.append("operational_evidence must be an array")
        return []
    ids: list[str] = []
    for index, item in enumerate(value):
        label = f"operational_evidence[{index}]"
        if not _exact_keys(item, OPERATIONAL_KEYS, label, issues):
            continue
        item_id = item["id"]
        if not isinstance(item_id, str) or not re.fullmatch(r"[a-z0-9_]+", item_id):
            issues.append(f"{label}.id is invalid")
        else:
            ids.append(item_id)
        if item["status"] not in {
            "passed",
            "failed",
            "not_applicable",
            "unavailable",
        }:
            issues.append(f"{label}.status is invalid")
        if item["detail"] is not None and not isinstance(item["detail"], str):
            issues.append(f"{label}.detail must be string or null")
        if not isinstance(item["evidence"], list) or not all(
            isinstance(entry, str) for entry in item["evidence"]
        ):
            issues.append(f"{label}.evidence must be an array of strings")
    if len(ids) != len(set(ids)):
        issues.append("operational_evidence contains duplicate IDs")
    return ids


def validate_result_bundle(
    bundle: Any,
    *,
    metadata: dict[str, Any],
    evaluator_manifest: dict[str, Any],
    fixture_manifest: dict[str, Any],
    workspace: Path,
) -> list[str]:
    issues: list[str] = []
    if not _exact_keys(bundle, BUNDLE_KEYS, "result bundle", issues):
        return issues
    if bundle["schema_version"] != "1.0.0":
        issues.append("result bundle schema_version must be 1.0.0")
    if bundle["run_id"] != metadata["run_id"]:
        issues.append("result bundle run_id disagrees with metadata")
    if bundle["task_id"] != metadata["task"]["task_id"]:
        issues.append("result bundle task_id disagrees with metadata")
    workspace_hash = bundle["workspace_sha256"]
    if not isinstance(workspace_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", workspace_hash):
        issues.append("workspace_sha256 must be a lowercase SHA-256 digest")
    else:
        observed_hash = repository_hash(workspace, fixture_manifest)
        if workspace_hash != observed_hash:
            issues.append(
                f"result bundle workspace hash mismatch: expected {observed_hash}, "
                f"observed {workspace_hash}"
            )
    if not isinstance(bundle["evaluator_version"], str) or not bundle["evaluator_version"]:
        issues.append("evaluator_version must be a non-empty string")
    try:
        _parse_datetime(bundle["evaluated_at"], "evaluated_at")
    except FinalizationError as error:
        issues.append(str(error))

    functional_ids = _validate_check_results(
        bundle["functional_tests"], "functional_tests", issues
    )
    architecture_ids = _validate_check_results(
        bundle["architecture_checks"], "architecture_checks", issues
    )
    operational_ids = _validate_operational_results(
        bundle["operational_evidence"], issues
    )
    error = bundle["evaluation_error"]
    if error is not None:
        if _exact_keys(error, {"classification", "detail"}, "evaluation_error", issues):
            if error["classification"] not in {
                "evaluator_error",
                "infrastructure_failure",
            }:
                issues.append("evaluation_error.classification is invalid")
            if not isinstance(error["detail"], str) or not error["detail"]:
                issues.append("evaluation_error.detail must be a non-empty string")
    else:
        expected_functional = [item["id"] for item in evaluator_manifest["functional_tests"]]
        expected_architecture = [item["id"] for item in evaluator_manifest["architecture_checks"]]
        expected_operational = [item["id"] for item in evaluator_manifest["operational_evidence"]]
        if functional_ids != expected_functional:
            issues.append(
                "functional result IDs/order must exactly match the approved manifest"
            )
        if architecture_ids != expected_architecture:
            issues.append(
                "architecture result IDs/order must exactly match the approved manifest"
            )
        if operational_ids != expected_operational:
            issues.append(
                "operational result IDs/order must exactly match the approved manifest"
            )
    if not isinstance(bundle["docker_status"], str):
        issues.append("docker_status must be a string")
    if not isinstance(bundle["docker_logs"], str):
        issues.append("docker_logs must be a string")
    if not isinstance(bundle["database_checks"], dict):
        issues.append("database_checks must be an object")
    return issues


def _run_git_bytes(
    workspace: Path,
    arguments: list[str],
    environment: dict[str, str],
) -> bytes:
    completed = subprocess.run(
        [find_git(), *arguments],
        cwd=workspace,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")
        raise FinalizationError(
            f"Git command failed ({completed.returncode}): "
            f"git {' '.join(arguments)}\n{detail}"
        )
    return completed.stdout


def generate_final_diff(
    workspace: Path,
    start_commit: str,
    *,
    excluded_untracked_paths: list[str] | None = None,
) -> bytes:
    workspace = workspace.resolve()
    if not start_commit_exists(workspace, start_commit):
        raise FinalizationError(f"Workspace is missing start commit {start_commit}")
    with tempfile.TemporaryDirectory(prefix="tsb-final-index-") as temporary:
        index_path = Path(temporary) / "index"
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(index_path)
        _run_git_bytes(workspace, ["read-tree", start_commit], environment)
        _run_git_bytes(workspace, ["add", "--all"], environment)
        excluded = set(excluded_untracked_paths or [])
        if excluded:
            added_raw = _run_git_bytes(
                workspace,
                [
                    "diff",
                    "--cached",
                    "--name-only",
                    "--diff-filter=A",
                    "-z",
                    start_commit,
                ],
                environment,
            )
            added_paths = {
                item.decode("utf-8", errors="surrogateescape")
                for item in added_raw.split(b"\0")
                if item
            }
            for relative_path in sorted(excluded.intersection(added_paths)):
                _run_git_bytes(
                    workspace,
                    ["update-index", "--force-remove", "--", relative_path],
                    environment,
                )
        return _run_git_bytes(
            workspace,
            ["diff", "--cached", "--binary", "--no-ext-diff", start_commit],
            environment,
        )


def _diagnostic_summary(results: list[dict[str, Any]]) -> dict[str, int | float]:
    applicable = [item for item in results if item["applicable"]]
    if not applicable:
        raise FinalizationError("A diagnostic result group has no applicable checks")
    passed = sum(1 for item in applicable if item["passed"] is True)
    return {
        "passed": passed,
        "applicable": len(applicable),
        "proportion": passed / len(applicable),
    }


def _atomic_write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    write_json(temporary, value)
    temporary.replace(path)


def _prepare_timing_and_stop(
    metadata: dict[str, Any],
    *,
    stop_reason: str,
    started_at: str | None,
    ended_at: str | None,
    stop_detail: str | None,
) -> None:
    if stop_reason not in VALID_STOP_REASONS:
        raise FinalizationError(f"Unsupported stop reason: {stop_reason}")
    existing_started = metadata["timing"]["started_at"]
    existing_ended = metadata["timing"]["ended_at"]
    start_text = started_at or existing_started
    end_text = ended_at or existing_ended
    if not start_text or not end_text:
        raise FinalizationError("Finalization requires started_at and ended_at")
    start = _parse_datetime(start_text, "started_at")
    end = _parse_datetime(end_text, "ended_at")
    wall_elapsed = (end - start).total_seconds()
    if wall_elapsed < 0:
        raise FinalizationError("ended_at cannot precede started_at")
    existing_elapsed = metadata["timing"].get("elapsed_seconds")
    preserve_recorded_elapsed = (
        started_at is None
        and ended_at is None
        and isinstance(existing_elapsed, (int, float))
        and not isinstance(existing_elapsed, bool)
        and existing_elapsed >= 0
    )
    elapsed = existing_elapsed if preserve_recorded_elapsed else wall_elapsed
    metadata["timing"] = {
        "started_at": start_text,
        "ended_at": end_text,
        "elapsed_seconds": elapsed,
    }
    interface = metadata["system"]["evaluation_interface"]
    submission_signal = None
    if stop_reason == "submitted":
        if interface == "api_wrapper":
            submission_signal = "api_submit_marker"
        elif interface == "native_ide":
            submission_signal = "native_visible_completion"
    metadata["stopping"] = {
        "reason": stop_reason,
        "detail": stop_detail,
        "submission_signal": submission_signal,
        "submit_marker_seen": submission_signal == "api_submit_marker",
    }


def finalize_run(
    evidence_directory: Path,
    workspace: Path,
    result_bundle_path: Path,
    *,
    stop_reason: str,
    started_at: str | None = None,
    ended_at: str | None = None,
    stop_detail: str | None = None,
) -> dict[str, Any]:
    evidence_directory = evidence_directory.resolve()
    workspace = workspace.resolve()
    metadata_path = evidence_directory / "metadata.json"
    metadata = load_json(metadata_path)
    if metadata["lifecycle_state"] in {"successful", "unsuccessful", "invalidated"}:
        raise FinalizationError("Refusing to finalize an already-terminal run")
    task_root = TASKS_ROOT / metadata["task"]["task_id"]
    evaluator_manifest = load_json(task_root / "evaluator_manifest.json")
    fixture_manifest = load_json(task_root / "fixture_manifest.json")
    if evaluator_manifest.get("review_status") != "approved":
        raise FinalizationError("Evaluator manifest is not approved")
    tracking = fixture_manifest.get("evaluator_manifest", {})
    if tracking.get("post_change_full_cycle_revalidation_required") is not False:
        raise FinalizationError("Task still requires full-cycle evaluator revalidation")

    bundle = load_json(result_bundle_path.resolve())
    issues = validate_result_bundle(
        bundle,
        metadata=metadata,
        evaluator_manifest=evaluator_manifest,
        fixture_manifest=fixture_manifest,
        workspace=workspace,
    )
    if issues:
        raise FinalizationError("Invalid result bundle:\n- " + "\n- ".join(issues))
    policy_path = evidence_directory / POLICY_SNAPSHOT_NAME
    inventory_path = evidence_directory / INVENTORY_NAME
    incidental_inventory: dict[str, Any] | None = None
    if policy_path.exists() or inventory_path.exists():
        if not policy_path.is_file() or not inventory_path.is_file():
            raise FinalizationError(
                "Workspace artifact policy snapshot and inventory must both exist"
            )
        try:
            artifact_policy = load_policy(policy_path)
            policy_issues = validate_hash_exclusion_alignment(
                artifact_policy, fixture_manifest
            )
            if policy_issues:
                raise WorkspaceArtifactPolicyError("; ".join(policy_issues))
            incidental_inventory = build_inventory(
                policy_path=policy_path,
                policy=artifact_policy,
                workspace=workspace,
                status="completed",
            )
        except WorkspaceArtifactPolicyError as error:
            raise FinalizationError(str(error)) from error
    final_diff = generate_final_diff(
        workspace,
        metadata["task"]["start_commit"],
        excluded_untracked_paths=(
            [item["path"] for item in incidental_inventory["entries"]]
            if incidental_inventory is not None
            else None
        ),
    )

    _prepare_timing_and_stop(
        metadata,
        stop_reason=stop_reason,
        started_at=started_at,
        ended_at=ended_at,
        stop_detail=stop_detail,
    )
    metadata["lifecycle_state"] = "evaluating"
    metadata["validity_status"] = "pending"
    metadata["results"]["success"] = None
    _atomic_write_json(metadata_path, metadata)

    evaluator_directory = evidence_directory / "evaluator"
    evaluator_directory.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(evaluator_directory / "result_bundle.json", bundle)
    status = "error" if bundle["evaluation_error"] else "completed"
    _atomic_write_json(
        evidence_directory / "hidden_test_results.json",
        {
            "schema_version": "1.0.0",
            "status": status,
            "evaluator_version": bundle["evaluator_version"],
            "evaluated_at": bundle["evaluated_at"],
            "tests": bundle["functional_tests"],
        },
    )
    _atomic_write_json(
        evidence_directory / "architecture_checks.json",
        {
            "schema_version": "1.0.0",
            "status": status,
            "evaluator_version": bundle["evaluator_version"],
            "evaluated_at": bundle["evaluated_at"],
            "checks": bundle["architecture_checks"],
        },
    )
    _atomic_write_json(
        evidence_directory / "database_checks.json",
        {
            "schema_version": "1.0.0",
            "status": status,
            "checks": bundle["database_checks"].get("checks", []),
            "details": bundle["database_checks"],
        },
    )
    (evidence_directory / "docker_status.txt").write_text(
        bundle["docker_status"], encoding="utf-8"
    )
    (evidence_directory / "docker_logs.txt").write_text(
        bundle["docker_logs"], encoding="utf-8"
    )
    (evidence_directory / "final.diff").write_bytes(final_diff)
    if incidental_inventory is not None:
        _atomic_write_json(inventory_path, incidental_inventory)

    evaluation_error = bundle["evaluation_error"]
    if evaluation_error:
        original_reason = metadata["stopping"]["reason"]
        metadata["lifecycle_state"] = "invalidated"
        metadata["validity_status"] = "invalid"
        metadata["stopping"] = {
            "reason": evaluation_error["classification"],
            "detail": (
                f"Original stop reason: {original_reason}. "
                f"{evaluation_error['detail']}"
            ),
            "submission_signal": None,
            "submit_marker_seen": False,
        }
        metadata["results"]["success"] = None
        metadata["results"]["functional_tests"] = {
            "passed": None,
            "applicable": None,
            "proportion": None,
        }
        metadata["results"]["architecture_checks"] = {
            "passed": None,
            "applicable": None,
            "proportion": None,
        }
        metadata["results"]["autonomous_success"] = None
    else:
        functional = _diagnostic_summary(bundle["functional_tests"])
        architecture = _diagnostic_summary(bundle["architecture_checks"])
        all_checks_pass = math.isclose(functional["proportion"], 1.0) and math.isclose(
            architecture["proportion"], 1.0
        )
        success = bool(all_checks_pass and stop_reason == "submitted")
        metadata["lifecycle_state"] = "successful" if success else "unsuccessful"
        metadata["validity_status"] = "valid"
        metadata["results"]["success"] = success
        metadata["results"]["functional_tests"] = functional
        metadata["results"]["architecture_checks"] = architecture
        metadata["results"]["autonomous_success"] = (
            success and metadata["clarification"]["responses"] == 0
            if metadata["results"]["robustness_eligible"]
            else None
        )
    _atomic_write_json(metadata_path, metadata)

    final_issues = validate_run(evidence_directory, workspace=workspace)
    if final_issues:
        # A rejected terminal record must remain recoverable. Preserve the
        # generated artifacts for diagnosis, but return metadata to an
        # explicitly non-terminal state so the evaluator can be rerun.
        metadata["lifecycle_state"] = "evaluating"
        metadata["validity_status"] = "pending"
        metadata["results"]["success"] = None
        metadata["results"]["functional_tests"] = {
            "passed": None,
            "applicable": None,
            "proportion": None,
        }
        metadata["results"]["architecture_checks"] = {
            "passed": None,
            "applicable": None,
            "proportion": None,
        }
        metadata["results"]["autonomous_success"] = None
        _atomic_write_json(metadata_path, metadata)
        raise FinalizationError(
            "Finalized evidence failed validation:\n- " + "\n- ".join(final_issues)
        )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finalize a TSB run from a structured evaluator result bundle."
    )
    parser.add_argument("evidence_directory", type=Path)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("result_bundle", type=Path)
    parser.add_argument("--stop-reason", choices=sorted(VALID_STOP_REASONS), required=True)
    parser.add_argument("--started-at")
    parser.add_argument("--ended-at")
    parser.add_argument("--stop-detail")
    arguments = parser.parse_args()
    metadata = finalize_run(
        arguments.evidence_directory,
        arguments.workspace,
        arguments.result_bundle,
        stop_reason=arguments.stop_reason,
        started_at=arguments.started_at,
        ended_at=arguments.ended_at,
        stop_detail=arguments.stop_detail,
    )
    print(f"run_id={metadata['run_id']}")
    print(f"lifecycle_state={metadata['lifecycle_state']}")
    print(f"success={metadata['results']['success']}")


if __name__ == "__main__":
    main()
