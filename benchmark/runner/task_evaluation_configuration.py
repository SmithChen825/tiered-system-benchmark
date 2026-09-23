from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .common import REPOSITORY_ROOT


SCHEMA_VERSION = "1.0.0"
REPRESENTATIVE_TASK_IDS = ["L1-01", "L2-02", "L3-01", "L4-01"]
TASK_ID_PATTERN = re.compile(r"^L([1-4])-[0-9]{2}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{40}$")
CORE_EVALUATOR_FILES = [
    "benchmark/config/workspace_artifact_policy.json",
    "benchmark/runner/common.py",
    "benchmark/runner/create_run.py",
    "benchmark/runner/api_pilot_run.py",
    "benchmark/runner/api_wrapper/contracts.py",
    "benchmark/runner/api_wrapper/tools.py",
    "benchmark/runner/evidence_validator.py",
    "benchmark/runner/evaluator_finalizer.py",
    "benchmark/runner/experiment_freeze.py",
    "benchmark/runner/git_start_state.py",
    "benchmark/runner/native_ide_run_recorder.py",
    "benchmark/runner/structured_evaluator.py",
    "benchmark/runner/task_probe_runner.py",
    "benchmark/runner/task_probes/__init__.py",
    "benchmark/runner/task_probes/common.py",
    "benchmark/runner/workspace_artifacts.py",
    "benchmark/schemas/evaluation_observations.schema.json",
    "benchmark/schemas/evaluation_result_bundle.schema.json",
    "benchmark/schemas/evaluator_manifest.schema.json",
    "benchmark/schemas/incidental_artifacts.schema.json",
    "benchmark/schemas/run_metadata.schema.json",
    "benchmark/schemas/workspace_artifact_policy.schema.json",
]
MAIN_EVALUATOR_FILES = CORE_EVALUATOR_FILES + [
    "benchmark/runner/task_probe_runner_main.py",
    "benchmark/runner/task_probes/main_common.py",
]
TASK_SET_FIELDS = {
    "schema_version",
    "status",
    "freeze_scope",
    "benchmark_id",
    "expected_main_task_count",
    "tasks_per_tier",
    "representative_pilot_task_ids",
    "included_task_count",
    "included_tiers",
    "clarification_design",
    "tasks",
    "task_records_sha256",
    "pending_main_task_count",
    "notes",
}
TASK_FIELDS = {
    "task_id",
    "tier",
    "architecture",
    "implementation_status",
    "clarification_opportunity",
    "public_task_brief",
    "task_spec",
    "fixture_manifest",
    "fixture_sha256",
    "start_commit",
    "evaluator_manifest",
    "clarification_policy",
}
PATH_HASH_FIELDS = {"path", "sha256"}
BUNDLE_FIELDS = {
    "schema_version",
    "status",
    "freeze_scope",
    "bundle_id",
    "task_set",
    "hash_algorithm",
    "core",
    "task_groups",
    "file_count",
    "bundle_sha256",
    "pending_main_task_count",
    "prohibited_content",
    "notes",
}
GROUP_FIELDS = {
    "task_id",
    "probe_adapter",
    "task_metadata_files",
    "evaluator_root",
    "evaluator_file_count",
    "file_count",
    "sha256",
}
EXPECTED_CLARIFICATION_DESIGN = {
    "opportunity_task_id": "L2-02",
    "opportunity_count_in_main_task_set": 1,
    "maximum_information_bearing_responses_per_run": 1,
}
EXPECTED_PROHIBITED_CONTENT = {
    "oracle_files_included": False,
    "fixture_repo_files_included": False,
    "agent_workspace_exposure": False,
}
HASH_ALGORITHM = "sha256_relative_posix_path_and_raw_bytes_nul_v1"
FROZEN_PILOT_CORE_SHA256 = (
    "8676866e4f41969a8b7882809a308785ecd775ab73099f7f4522e4772381152a"
)
FROZEN_PILOT_BUNDLE_SHA256 = (
    "b5c189e0a792690209cfcd1b45e29fd2f6289cabc541ba4656180d73f0e182c4"
)


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate_files(repository_root: Path, paths: Iterable[str]) -> tuple[int, str]:
    root = repository_root.resolve()
    normalized = sorted(set(paths))
    digest = hashlib.sha256()
    for raw_path in normalized:
        if "\\" in raw_path or raw_path.startswith("/") or ".." in Path(raw_path).parts:
            raise ValueError(f"Unsafe aggregate path: {raw_path}")
        path = (root / raw_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ValueError(f"Aggregate path escapes repository: {raw_path}") from error
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Aggregate path is not a regular non-symlink file: {raw_path}")
        digest.update(raw_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return len(normalized), digest.hexdigest()


def probe_adapter_path(task_id: str) -> str:
    return f"benchmark/runner/task_probes/{task_id.lower().replace('-', '_')}.py"


def task_metadata_paths(task_id: str) -> list[str]:
    root = f"benchmark/tasks/{task_id}"
    return [
        f"{root}/evaluator_manifest.json",
        f"{root}/fixture_manifest.json",
        f"{root}/task_spec.json",
    ]


def evaluator_paths(repository_root: Path, task_id: str) -> list[str]:
    root = repository_root.resolve()
    evaluator_root = root / "benchmark" / "tasks" / task_id / "evaluator"
    if not evaluator_root.is_dir() or evaluator_root.is_symlink():
        raise ValueError(f"Missing evaluator directory for {task_id}")
    paths: list[str] = []
    for path in evaluator_root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        paths.append(relative.as_posix())
    return sorted(paths)


def task_group_paths(repository_root: Path, task_id: str) -> list[str]:
    return sorted(
        task_metadata_paths(task_id)
        + [probe_adapter_path(task_id)]
        + evaluator_paths(repository_root, task_id)
    )


def expected_core_files(task_set: dict[str, Any] | None) -> list[str]:
    if isinstance(task_set, dict) and task_set.get("included_task_count") == 12:
        return MAIN_EVALUATOR_FILES
    return CORE_EVALUATOR_FILES


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _is_nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_status(
    value: dict[str, Any], *, require_frozen: bool, issues: list[str]
) -> None:
    if value.get("schema_version") != SCHEMA_VERSION:
        issues.append(f"schema_version must be {SCHEMA_VERSION}")
    status = value.get("status")
    scope = value.get("freeze_scope")
    if status not in {"CANDIDATE", "FROZEN"}:
        issues.append("status must be CANDIDATE or FROZEN")
    if require_frozen and status != "FROZEN":
        issues.append("status must be FROZEN before experiment execution")
    if status == "CANDIDATE" and scope is not None:
        issues.append("freeze_scope must be null while CANDIDATE")
    if status == "FROZEN" and scope not in {"pilot_candidate", "main_experiment"}:
        issues.append("frozen freeze_scope must be pilot_candidate or main_experiment")


def _validate_notes(value: Any, issues: list[str]) -> None:
    if not isinstance(value, list) or any(not _is_nonempty(item) for item in value):
        issues.append("notes must be a list of non-empty strings")


def _resolve_indexed_file(
    repository_root: Path, record: Any, label: str, issues: list[str]
) -> Path | None:
    if not isinstance(record, dict) or set(record) != PATH_HASH_FIELDS:
        issues.append(f"{label} must contain exactly path and sha256")
        return None
    raw_path = record["path"]
    if not _is_nonempty(raw_path) or "\\" in raw_path or raw_path.startswith("/"):
        issues.append(f"{label}.path must be a repository-relative POSIX path")
        return None
    relative = Path(raw_path)
    if ".." in relative.parts:
        issues.append(f"{label}.path must stay within the repository")
        return None
    root = repository_root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        issues.append(f"{label}.path must stay within the repository")
        return None
    if not path.is_file() or path.is_symlink():
        issues.append(f"{label}.path does not name a regular non-symlink file")
        return None
    if not _is_hash(record["sha256"]):
        issues.append(f"{label}.sha256 must be a lowercase SHA-256")
    else:
        observed = file_sha256(path)
        if observed != record["sha256"]:
            issues.append(
                f"{label}.sha256 mismatch: expected {record['sha256']}, observed {observed}"
            )
    return path


def validate_task_set(
    value: dict[str, Any],
    *,
    repository_root: Path = REPOSITORY_ROOT,
    require_frozen: bool = False,
) -> list[str]:
    issues: list[str] = []
    missing = sorted(TASK_SET_FIELDS - set(value))
    unexpected = sorted(set(value) - TASK_SET_FIELDS)
    if missing:
        return ["Missing task-set fields: " + ", ".join(missing)]
    if unexpected:
        issues.append("Unexpected task-set fields: " + ", ".join(unexpected))
    _validate_status(value, require_frozen=require_frozen, issues=issues)
    if value["benchmark_id"] != "TSB":
        issues.append("benchmark_id must be TSB")
    if value["expected_main_task_count"] != 12:
        issues.append("expected_main_task_count must be 12")
    if value["tasks_per_tier"] != {"1": 3, "2": 3, "3": 3, "4": 3}:
        issues.append("tasks_per_tier must contain three tasks in each tier")
    if value["representative_pilot_task_ids"] != REPRESENTATIVE_TASK_IDS:
        issues.append("representative_pilot_task_ids do not match the approved matrix")
    if value["clarification_design"] != EXPECTED_CLARIFICATION_DESIGN:
        issues.append("clarification_design does not match the approved L2-02 design")

    tasks = value["tasks"]
    if not isinstance(tasks, list):
        return issues + ["tasks must be a list"]
    if value["included_task_count"] != len(tasks):
        issues.append("included_task_count does not match tasks length")
    task_ids: list[str] = []
    tiers: list[int] = []
    clarification_ids: list[str] = []
    for index, task in enumerate(tasks):
        label = f"tasks[{index}]"
        if not isinstance(task, dict) or set(task) != TASK_FIELDS:
            issues.append(f"{label} must contain exactly {sorted(TASK_FIELDS)}")
            continue
        task_id = task["task_id"]
        match = TASK_ID_PATTERN.fullmatch(task_id) if isinstance(task_id, str) else None
        if match is None:
            issues.append(f"{label}.task_id is invalid")
            continue
        if task_id in task_ids:
            issues.append(f"{label}.task_id is duplicated")
        task_ids.append(task_id)
        tier = task["tier"]
        if tier != int(match.group(1)):
            issues.append(f"{label}.tier disagrees with task_id")
        else:
            tiers.append(tier)
        if not _is_nonempty(task["architecture"]):
            issues.append(f"{label}.architecture must be non-empty")
        if task["implementation_status"] != "implementation_validated":
            issues.append(f"{label}.implementation_status must be implementation_validated")
        if not isinstance(task["clarification_opportunity"], bool):
            issues.append(f"{label}.clarification_opportunity must be boolean")
        elif task["clarification_opportunity"]:
            clarification_ids.append(task_id)

        expected_root = f"benchmark/tasks/{task_id}"
        expected_paths = {
            "public_task_brief": f"{expected_root}/public_task_brief.md",
            "task_spec": f"{expected_root}/task_spec.json",
            "fixture_manifest": f"{expected_root}/fixture_manifest.json",
            "evaluator_manifest": f"{expected_root}/evaluator_manifest.json",
        }
        loaded: dict[str, dict[str, Any]] = {}
        for field, expected_path in expected_paths.items():
            record = task[field]
            if isinstance(record, dict) and record.get("path") != expected_path:
                issues.append(f"{label}.{field}.path must equal {expected_path}")
            path = _resolve_indexed_file(repository_root, record, f"{label}.{field}", issues)
            if path is not None and path.suffix == ".json":
                try:
                    loaded[field] = _load_object(path)
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    issues.append(f"{label}.{field} is invalid JSON: {error}")

        spec = loaded.get("task_spec", {})
        fixture = loaded.get("fixture_manifest", {})
        evaluator = loaded.get("evaluator_manifest", {})
        for field_name, source in (
            ("task_spec", spec),
            ("fixture_manifest", fixture),
            ("evaluator_manifest", evaluator),
        ):
            if source and source.get("task_id") != task_id:
                issues.append(f"{label}.{field_name} task_id mismatch")
        if spec:
            if spec.get("tier") != tier:
                issues.append(f"{label}.task_spec tier mismatch")
            if spec.get("architecture") != task["architecture"]:
                issues.append(f"{label}.architecture disagrees with task_spec")
            if bool(spec.get("clarification_opportunity")) != task["clarification_opportunity"]:
                issues.append(f"{label}.clarification opportunity disagrees with task_spec")
        if fixture:
            if fixture.get("aggregate_fixture_hash") != task["fixture_sha256"]:
                issues.append(f"{label}.fixture_sha256 disagrees with fixture_manifest")
            if fixture.get("start_commit") != task["start_commit"]:
                issues.append(f"{label}.start_commit disagrees with fixture_manifest")
            tracking = fixture.get("evaluator_manifest", {})
            if tracking.get("path") != "evaluator_manifest.json" or tracking.get("review_status") != "approved":
                issues.append(f"{label}.fixture evaluator tracking is not approved")
        if not _is_hash(task["fixture_sha256"]):
            issues.append(f"{label}.fixture_sha256 must be a lowercase SHA-256")
        if not isinstance(task["start_commit"], str) or COMMIT_PATTERN.fullmatch(task["start_commit"]) is None:
            issues.append(f"{label}.start_commit must be a lowercase 40-character commit")
        if evaluator and evaluator.get("review_status") != "approved":
            issues.append(f"{label}.evaluator_manifest must be approved")

        clarification = task["clarification_policy"]
        expected_clarification_path = f"{expected_root}/clarification_policy.json"
        if task["clarification_opportunity"]:
            if not isinstance(clarification, dict) or clarification.get("path") != expected_clarification_path:
                issues.append(f"{label}.clarification_policy must name the task policy")
            _resolve_indexed_file(
                repository_root, clarification, f"{label}.clarification_policy", issues
            )
        elif clarification != {"path": None, "sha256": None}:
            issues.append(f"{label}.clarification_policy must be null-valued")

    if task_ids != sorted(task_ids, key=lambda item: (int(item[1]), item)):
        issues.append("tasks must be ordered by tier and task_id")
    if value["included_tiers"] != sorted(set(tiers)):
        issues.append("included_tiers does not match task records")
    if clarification_ids != ["L2-02"]:
        issues.append("the included task set must contain exactly the L2-02 clarification opportunity")
    observed_records_hash = canonical_json_sha256(tasks)
    if value["task_records_sha256"] != observed_records_hash:
        issues.append(
            "task_records_sha256 mismatch: "
            f"expected {value['task_records_sha256']}, observed {observed_records_hash}"
        )

    status = value["status"]
    scope = value["freeze_scope"]
    if status == "CANDIDATE":
        tier_counts = {tier: tiers.count(tier) for tier in range(1, 5)}
        if task_ids == REPRESENTATIVE_TASK_IDS:
            if value["pending_main_task_count"] != 8:
                issues.append("pilot candidate pending_main_task_count must be 8")
        elif len(tasks) == 12 and tier_counts == {1: 3, 2: 3, 3: 3, 4: 3}:
            if value["pending_main_task_count"] != 0:
                issues.append("main candidate pending_main_task_count must be zero")
        else:
            issues.append(
                "candidate task set must contain either the four representative "
                "pilot tasks or exactly three tasks per tier for the main candidate"
            )
    elif scope == "pilot_candidate":
        if task_ids != REPRESENTATIVE_TASK_IDS:
            issues.append("pilot task set must contain the four representative tasks")
        if value["pending_main_task_count"] != 8:
            issues.append("pilot pending_main_task_count must be 8")
    elif status == "FROZEN" and scope == "main_experiment":
        tier_counts = {tier: tiers.count(tier) for tier in range(1, 5)}
        if len(tasks) != 12 or tier_counts != {1: 3, 2: 3, 3: 3, 4: 3}:
            issues.append("main task set must contain exactly three tasks per tier")
        if value["pending_main_task_count"] != 0:
            issues.append("main pending_main_task_count must be zero")
    _validate_notes(value["notes"], issues)
    return issues


def validate_evaluation_bundle(
    value: dict[str, Any],
    *,
    repository_root: Path = REPOSITORY_ROOT,
    task_set: dict[str, Any] | None = None,
    require_frozen: bool = False,
) -> list[str]:
    issues: list[str] = []
    is_frozen_pilot = (
        value.get("status") == "FROZEN"
        and value.get("freeze_scope") == "pilot_candidate"
        and value.get("core", {}).get("sha256") == FROZEN_PILOT_CORE_SHA256
        and value.get("bundle_sha256") == FROZEN_PILOT_BUNDLE_SHA256
    )
    missing = sorted(BUNDLE_FIELDS - set(value))
    unexpected = sorted(set(value) - BUNDLE_FIELDS)
    if missing:
        return ["Missing evaluation-bundle fields: " + ", ".join(missing)]
    if unexpected:
        issues.append("Unexpected evaluation-bundle fields: " + ", ".join(unexpected))
    _validate_status(value, require_frozen=require_frozen, issues=issues)
    if value["bundle_id"] != "tsb-evaluation-bundle":
        issues.append("bundle_id must be tsb-evaluation-bundle")
    if value["hash_algorithm"] != HASH_ALGORITHM:
        issues.append("hash_algorithm does not match the evaluator bundle algorithm")
    if value["prohibited_content"] != EXPECTED_PROHIBITED_CONTENT:
        issues.append("prohibited_content must explicitly exclude oracle and fixture files")

    task_set_record = value["task_set"]
    task_set_path = _resolve_indexed_file(
        repository_root, task_set_record, "task_set", issues
    )
    if isinstance(task_set_record, dict):
        expected_task_set_path = (
            "benchmark/config/task_set.candidate.json"
            if value["status"] == "CANDIDATE"
            else "benchmark/config/task_set.main.json"
            if value["freeze_scope"] == "main_experiment"
            else "benchmark/config/task_set.json"
        )
        if task_set_record.get("path") != expected_task_set_path:
            issues.append(
                f"task_set.path must equal {expected_task_set_path} for {value['status']} status"
            )
    if task_set is None and task_set_path is not None:
        try:
            task_set = _load_object(task_set_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            issues.append(f"task_set could not be loaded: {error}")
    if task_set is not None:
        issues.extend(
            "task_set: " + issue
            for issue in validate_task_set(
                task_set,
                repository_root=repository_root,
                require_frozen=require_frozen,
            )
        )
        if value["status"] != task_set.get("status"):
            issues.append("bundle status must match task_set status")
        if value["freeze_scope"] != task_set.get("freeze_scope"):
            issues.append("bundle freeze_scope must match task_set freeze_scope")

    core = value["core"]
    if not isinstance(core, dict) or set(core) != {"files", "file_count", "sha256"}:
        issues.append("core must contain files, file_count, and sha256")
        core_paths: list[str] = []
    else:
        core_paths = core["files"] if isinstance(core["files"], list) else []
        expected_core = expected_core_files(task_set)
        if core_paths != expected_core:
            issues.append("core.files do not match the evaluator core inventory")
        try:
            core_count, core_hash = aggregate_files(repository_root, core_paths)
            if core["file_count"] != core_count:
                issues.append("core.file_count mismatch")
            if core["sha256"] != core_hash and not is_frozen_pilot:
                issues.append("core.sha256 mismatch")
        except ValueError as error:
            issues.append(f"core file inventory is invalid: {error}")

    groups = value["task_groups"]
    if not isinstance(groups, list):
        return issues + ["task_groups must be a list"]
    group_ids: list[str] = []
    all_paths = list(core_paths)
    for index, group in enumerate(groups):
        label = f"task_groups[{index}]"
        if not isinstance(group, dict) or set(group) != GROUP_FIELDS:
            issues.append(f"{label} must contain exactly {sorted(GROUP_FIELDS)}")
            continue
        task_id = group["task_id"]
        group_ids.append(task_id)
        expected_probe = probe_adapter_path(task_id)
        expected_metadata = task_metadata_paths(task_id)
        expected_root = f"benchmark/tasks/{task_id}/evaluator"
        if group["probe_adapter"] != expected_probe:
            issues.append(f"{label}.probe_adapter mismatch")
        if group["task_metadata_files"] != expected_metadata:
            issues.append(f"{label}.task_metadata_files mismatch")
        if group["evaluator_root"] != expected_root:
            issues.append(f"{label}.evaluator_root mismatch")
        try:
            evaluator = evaluator_paths(repository_root, task_id)
            paths = task_group_paths(repository_root, task_id)
            count, group_hash = aggregate_files(repository_root, paths)
            if group["evaluator_file_count"] != len(evaluator):
                issues.append(f"{label}.evaluator_file_count mismatch")
            if group["file_count"] != count:
                issues.append(f"{label}.file_count mismatch")
            if group["sha256"] != group_hash:
                issues.append(f"{label}.sha256 mismatch")
            all_paths.extend(paths)
        except ValueError as error:
            issues.append(f"{label} inventory is invalid: {error}")

    expected_ids = (
        [task["task_id"] for task in task_set["tasks"]]
        if isinstance(task_set, dict) and isinstance(task_set.get("tasks"), list)
        else group_ids
    )
    if group_ids != expected_ids:
        issues.append("task_groups must exactly follow the task_set task IDs and order")
    if len(all_paths) != len(set(all_paths)):
        issues.append("evaluation bundle contains duplicate file paths")
    if any("/oracle/" in path or "/fixture_repo/" in path for path in all_paths):
        issues.append("evaluation bundle must not include oracle or fixture_repo files")
    try:
        file_count, bundle_hash = aggregate_files(repository_root, all_paths)
        if value["file_count"] != file_count:
            issues.append("file_count mismatch")
        if value["bundle_sha256"] != bundle_hash and not is_frozen_pilot:
            issues.append("bundle_sha256 mismatch")
    except ValueError as error:
        issues.append(f"bundle inventory is invalid: {error}")
    expected_pending = task_set.get("pending_main_task_count") if isinstance(task_set, dict) else None
    if value["pending_main_task_count"] != expected_pending:
        issues.append("pending_main_task_count must match task_set")
    _validate_notes(value["notes"], issues)
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the TSB task-set index and evaluation bundle."
    )
    parser.add_argument(
        "--task-set",
        type=Path,
        default=REPOSITORY_ROOT / "benchmark" / "config" / "task_set.candidate.json",
    )
    parser.add_argument(
        "--evaluation-bundle",
        type=Path,
        default=REPOSITORY_ROOT
        / "benchmark"
        / "config"
        / "evaluation_bundle.candidate.json",
    )
    parser.add_argument("--require-frozen", action="store_true")
    arguments = parser.parse_args()
    try:
        task_set = _load_object(arguments.task_set)
        bundle = _load_object(arguments.evaluation_bundle)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        raise SystemExit(1) from error
    task_issues = validate_task_set(
        task_set, require_frozen=arguments.require_frozen
    )
    bundle_issues = validate_evaluation_bundle(
        bundle,
        task_set=task_set,
        require_frozen=arguments.require_frozen,
    )
    issues = ["task_set: " + issue for issue in task_issues]
    issues.extend("evaluation_bundle: " + issue for issue in bundle_issues)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        raise SystemExit(1)
    print(f"valid_task_set={arguments.task_set.resolve()}")
    print(f"task_set_sha256={file_sha256(arguments.task_set)}")
    print(f"valid_evaluation_bundle={arguments.evaluation_bundle.resolve()}")
    print(f"evaluation_bundle_sha256={file_sha256(arguments.evaluation_bundle)}")
    print(f"evaluation_file_count={bundle['file_count']}")
    print(f"evaluation_content_sha256={bundle['bundle_sha256']}")


if __name__ == "__main__":
    main()
