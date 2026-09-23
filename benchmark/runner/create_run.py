from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

try:
    from .common import (
        ARTIFACT_PATHS,
        REPOSITORY_ROOT,
        SYSTEM_PROFILES,
        TASKS_ROOT,
        build_run_id,
        load_json,
        repository_hash,
        sha256_bytes,
        write_json,
    )
    from .git_start_state import initialize_start_commit
    from .experiment_freeze import (
        validate_amendment_log,
        validate_experiment_freeze,
    )
    from .workspace_artifacts import (
        INVENTORY_NAME,
        POLICY_SNAPSHOT_NAME,
        POLICY_SOURCE_PATH,
        build_inventory,
        install_git_excludes,
        load_policy,
        validate_hash_exclusion_alignment,
    )
except ImportError:  # Supports direct script execution.
    from common import (  # type: ignore
        ARTIFACT_PATHS,
        REPOSITORY_ROOT,
        SYSTEM_PROFILES,
        TASKS_ROOT,
        build_run_id,
        load_json,
        repository_hash,
        sha256_bytes,
        write_json,
    )
    from git_start_state import initialize_start_commit  # type: ignore
    from experiment_freeze import (  # type: ignore
        validate_amendment_log,
        validate_experiment_freeze,
    )
    from workspace_artifacts import (  # type: ignore
        INVENTORY_NAME,
        POLICY_SNAPSHOT_NAME,
        POLICY_SOURCE_PATH,
        build_inventory,
        install_git_excludes,
        load_policy,
        validate_hash_exclusion_alignment,
    )


PILOT_API_ACTION_LIMIT = 15
PILOT_COMMAND_TIMEOUT_SECONDS = 180
PILOT_CONSECUTIVE_NO_ACTION_RESPONSE_LIMIT = 3
def _validate_experiment_execution_gate(phase: str) -> None:
    if phase not in {"pilot", "main"}:
        return
    freeze_name = "experiment_freeze.main.json" if phase == "main" else "experiment_freeze.json"
    experiment_freeze_path = REPOSITORY_ROOT / "benchmark" / "config" / freeze_name
    if not experiment_freeze_path.is_file():
        raise ValueError(
            "A complete FROZEN experiment manifest is required before pilot or main runs"
        )
    try:
        manifest = load_json(experiment_freeze_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"Experiment freeze manifest is invalid: {error}") from error
    issues = validate_experiment_freeze(
        manifest,
        repository_root=REPOSITORY_ROOT,
        require_frozen=True,
        verify_files=True,
    )
    if issues:
        raise ValueError("Experiment execution freeze gate failed: " + "; ".join(issues))
    amendment = manifest.get("amendment_log")
    if not isinstance(amendment, dict) or not isinstance(amendment.get("path"), str):
        raise ValueError(
            "Experiment execution freeze gate failed: manifest does not identify an amendment log"
        )
    amendment_path = (REPOSITORY_ROOT / amendment["path"]).resolve()
    try:
        amendment_path.relative_to(REPOSITORY_ROOT.resolve())
        log = load_json(amendment_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"Experiment amendment log is invalid: {error}") from error
    issues = validate_amendment_log(
        log,
        expected_freeze_id=manifest.get("freeze_id"),
        expected_manifest_sha256=manifest.get("manifest_sha256"),
        require_bound=True,
        require_resolved=True,
    )
    if issues:
        raise ValueError("Experiment execution freeze gate failed: " + "; ".join(issues))


def _diagnostic_placeholder() -> dict[str, int | float | None]:
    return {"passed": None, "applicable": None, "proportion": None}


def _initial_metadata(
    *,
    run_id: str,
    phase: str,
    task_spec: dict[str, Any],
    fixture_manifest: dict[str, Any],
    prompt_bytes: bytes,
    system_id: str,
    system_slug: str,
    evaluation_interface: str,
    repetition: int,
    attempt: int,
) -> dict[str, Any]:
    tier = int(task_spec["tier"])
    usage_status = (
        "not_applicable"
        if evaluation_interface == "researcher_validation"
        else "unavailable"
    )
    return {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "phase": phase,
        "lifecycle_state": "prepared",
        "validity_status": "pending",
        "task": {
            "task_id": task_spec["task_id"],
            "tier": tier,
            "repetition": repetition,
            "attempt": attempt,
            "fixture_sha256": fixture_manifest["aggregate_fixture_hash"],
            "prompt_sha256": sha256_bytes(prompt_bytes),
            "start_commit": fixture_manifest["start_commit"],
            "clarification_opportunity": bool(
                task_spec["clarification_opportunity"]
            ),
        },
        "system": {
            "system_id": system_id,
            "system_slug": system_slug,
            "evaluation_interface": evaluation_interface,
            "product_version": None,
            "model_identifier": None,
            "provider_endpoint": None,
            "configuration_sha256": None,
        },
        "schedule": {"order_position": None, "random_seed": None},
        "timing": {
            "started_at": None,
            "ended_at": None,
            "elapsed_seconds": None,
        },
        "limits": {
            "task_wall_clock_seconds": None,
            "api_action_limit": (
                (30 if phase == "main" else PILOT_API_ACTION_LIMIT)
                if evaluation_interface == "api_wrapper"
                else None
            ),
            "command_timeout_seconds": (
                PILOT_COMMAND_TIMEOUT_SECONDS
                if evaluation_interface == "api_wrapper"
                else None
            ),
            "consecutive_no_action_response_limit": (
                PILOT_CONSECUTIVE_NO_ACTION_RESPONSE_LIMIT
                if evaluation_interface == "api_wrapper"
                else None
            ),
        },
        "stopping": {
            "reason": None,
            "detail": None,
            "submission_signal": None,
            "submit_marker_seen": False,
        },
        "results": {
            "success": None,
            "functional_tests": _diagnostic_placeholder(),
            "architecture_checks": _diagnostic_placeholder(),
            "robustness_eligible": (
                phase in {"pilot", "main"} and tier in {3, 4}
            ),
            "autonomous_success": None,
        },
        "clarification": {
            "opportunity": bool(task_spec["clarification_opportunity"]),
            "requests": 0,
            "authorized_requests": 0,
            "responses": 0,
        },
        "usage": {
            "status": usage_status,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "monetary_cost": None,
            "currency": None,
        },
        "artifacts": dict(ARTIFACT_PATHS),
    }


def _write_placeholders(evidence_directory: Path, prompt_bytes: bytes) -> None:
    (evidence_directory / ARTIFACT_PATHS["task_prompt"]).write_bytes(prompt_bytes)
    (evidence_directory / ARTIFACT_PATHS["transcript"]).write_text(
        "[NOT_YET_AVAILABLE]\n", encoding="utf-8"
    )
    availability_record = {
        "record_type": "availability",
        "status": "not_started",
        "reason": "Run has been prepared but execution has not started.",
    }
    for key in ("raw_model_response", "adapter_decisions"):
        (evidence_directory / ARTIFACT_PATHS[key]).write_text(
            json.dumps(availability_record, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    write_json(
        evidence_directory / ARTIFACT_PATHS["clarification_log"],
        {"schema_version": "1.0.0", "status": "not_started", "events": []},
    )
    write_json(
        evidence_directory / ARTIFACT_PATHS["hidden_test_results"],
        {"schema_version": "1.0.0", "status": "not_run", "tests": []},
    )
    write_json(
        evidence_directory / ARTIFACT_PATHS["architecture_checks"],
        {"schema_version": "1.0.0", "status": "not_run", "checks": []},
    )
    for key in ("docker_status", "docker_logs"):
        (evidence_directory / ARTIFACT_PATHS[key]).write_text(
            "[NOT_YET_CAPTURED]\n", encoding="utf-8"
        )
    write_json(
        evidence_directory / ARTIFACT_PATHS["database_checks"],
        {
            "schema_version": "1.0.0",
            "status": "not_run",
            "checks": [],
        },
    )
    (evidence_directory / ARTIFACT_PATHS["final_diff"]).write_bytes(b"")


def create_run(
    *,
    task_id: str,
    system_id: str,
    phase: str,
    repetition: int,
    attempt: int,
    runs_root: Path,
    workspaces_root: Path,
) -> tuple[Path, Path]:
    if phase not in {"validation", "pilot", "main"}:
        raise ValueError(f"Unsupported phase: {phase}")
    if system_id not in SYSTEM_PROFILES:
        raise ValueError(f"Unsupported system: {system_id}")
    if not 1 <= repetition <= 99 or not 1 <= attempt <= 99:
        raise ValueError("repetition and attempt must be between 1 and 99")
    if phase in {"pilot", "main"} and system_id in {"baseline", "oracle"}:
        raise ValueError("baseline/oracle actors are validation-only")

    task_root = TASKS_ROOT / task_id
    required_sources = [
        task_root / "task_spec.json",
        task_root / "fixture_manifest.json",
        task_root / "evaluator_manifest.json",
        task_root / "public_task_brief.md",
        task_root / "fixture_repo",
    ]
    missing_sources = [str(path) for path in required_sources if not path.exists()]
    if missing_sources:
        raise FileNotFoundError(
            "Task package is incomplete: " + ", ".join(missing_sources)
        )

    task_spec = load_json(task_root / "task_spec.json")
    fixture_manifest = load_json(task_root / "fixture_manifest.json")
    if task_spec.get("task_id") != task_id or fixture_manifest.get("task_id") != task_id:
        raise ValueError("Task ID is inconsistent across the task package")
    artifact_policy = load_policy(POLICY_SOURCE_PATH)
    if phase in {"pilot", "main"} and artifact_policy["status"] != "FROZEN":
        raise ValueError(
            "Workspace artifact policy must be FROZEN before pilot or main runs"
        )
    _validate_experiment_execution_gate(phase)
    policy_issues = validate_hash_exclusion_alignment(
        artifact_policy, fixture_manifest
    )
    if policy_issues:
        raise ValueError("; ".join(policy_issues))

    system_slug, evaluation_interface = SYSTEM_PROFILES[system_id]
    run_id = build_run_id(phase, task_id, system_slug, repetition, attempt)
    resolved_runs_root = runs_root.resolve()
    resolved_workspaces_root = workspaces_root.resolve()
    if (
        resolved_runs_root == resolved_workspaces_root
        or resolved_runs_root.is_relative_to(resolved_workspaces_root)
        or resolved_workspaces_root.is_relative_to(resolved_runs_root)
    ):
        raise ValueError("runs_root and workspaces_root must be separate trust zones")
    if resolved_runs_root.is_relative_to(TASKS_ROOT) or resolved_workspaces_root.is_relative_to(
        TASKS_ROOT
    ):
        raise ValueError("Run outputs must not be created inside researcher task packages")
    fixture_root = task_root / "fixture_repo"
    source_links = [path for path in fixture_root.rglob("*") if path.is_symlink()]
    if source_links:
        raise ValueError(
            "Frozen fixture contains symbolic links and cannot be isolated safely: "
            + ", ".join(str(path) for path in source_links)
        )

    evidence_directory = resolved_runs_root / run_id
    workspace_directory = resolved_workspaces_root / run_id / "repo"
    if evidence_directory.exists() or workspace_directory.parent.exists():
        raise FileExistsError(f"Refusing to overwrite existing run: {run_id}")

    prompt_bytes = (task_root / "public_task_brief.md").read_bytes()
    workspace_created = False
    evidence_created = False
    try:
        workspace_directory.parent.mkdir(parents=True, exist_ok=False)
        shutil.copytree(fixture_root, workspace_directory)
        workspace_created = True
        observed_hash = repository_hash(workspace_directory, fixture_manifest)
        expected_hash = fixture_manifest.get("aggregate_fixture_hash")
        if observed_hash != expected_hash:
            raise RuntimeError(
                f"Prepared workspace hash mismatch: expected {expected_hash}, "
                f"observed {observed_hash}"
            )
        observed_commit = initialize_start_commit(workspace_directory, task_id)
        expected_commit = fixture_manifest.get("start_commit")
        if observed_commit != expected_commit:
            raise RuntimeError(
                f"Prepared workspace start commit mismatch: expected "
                f"{expected_commit}, observed {observed_commit}"
            )
        install_git_excludes(workspace_directory, artifact_policy)

        evidence_directory.mkdir(parents=True, exist_ok=False)
        evidence_created = True
        policy_snapshot = evidence_directory / POLICY_SNAPSHOT_NAME
        shutil.copy2(POLICY_SOURCE_PATH, policy_snapshot)
        write_json(
            evidence_directory / INVENTORY_NAME,
            build_inventory(
                policy_path=policy_snapshot,
                policy=artifact_policy,
                workspace=workspace_directory,
                status="not_scanned",
            ),
        )
        metadata = _initial_metadata(
            run_id=run_id,
            phase=phase,
            task_spec=task_spec,
            fixture_manifest=fixture_manifest,
            prompt_bytes=prompt_bytes,
            system_id=system_id,
            system_slug=system_slug,
            evaluation_interface=evaluation_interface,
            repetition=repetition,
            attempt=attempt,
        )
        write_json(evidence_directory / "metadata.json", metadata)
        _write_placeholders(evidence_directory, prompt_bytes)
    except Exception:
        if evidence_created:
            shutil.rmtree(evidence_directory, ignore_errors=True)
        if workspace_created or workspace_directory.parent.exists():
            shutil.rmtree(workspace_directory.parent, ignore_errors=True)
        raise
    return evidence_directory, workspace_directory


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an isolated TSB workspace and evidence directory."
    )
    parser.add_argument("task_id")
    parser.add_argument("system_id", choices=sorted(SYSTEM_PROFILES))
    parser.add_argument("--phase", choices=["validation", "pilot", "main"], default="validation")
    parser.add_argument("--repetition", type=int, default=1)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--runs-root", type=Path, default=REPOSITORY_ROOT / "runs")
    parser.add_argument(
        "--workspaces-root", type=Path, default=REPOSITORY_ROOT / "workspaces"
    )
    arguments = parser.parse_args()
    evidence, workspace = create_run(
        task_id=arguments.task_id,
        system_id=arguments.system_id,
        phase=arguments.phase,
        repetition=arguments.repetition,
        attempt=arguments.attempt,
        runs_root=arguments.runs_root,
        workspaces_root=arguments.workspaces_root,
    )
    print(f"run_id={evidence.name}")
    print(f"evidence={evidence}")
    print(f"workspace={workspace}")


if __name__ == "__main__":
    main()
