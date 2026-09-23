from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

try:
    from .common import REPOSITORY_ROOT, hash_exclusions
    from .git_start_state import find_git
except ImportError:  # Supports direct script execution.
    from common import REPOSITORY_ROOT, hash_exclusions  # type: ignore
    from git_start_state import find_git  # type: ignore


POLICY_SOURCE_PATH = (
    REPOSITORY_ROOT / "benchmark" / "config" / "workspace_artifact_policy.json"
)
POLICY_SNAPSHOT_NAME = "workspace_artifact_policy.json"
INVENTORY_NAME = "incidental_artifacts.json"
POLICY_KEYS = {
    "schema_version",
    "status",
    "policy_id",
    "effective_scope",
    "historical_run_rule",
    "classifications",
    "controls",
}
CLASSIFICATION_KEYS = {
    "id",
    "untracked_only",
    "directory_names",
    "suffixes",
    "treatment",
}
CONTROL_VALUES = {
    "preserve_files_after_freeze": True,
    "tracked_changes_always_in_final_diff": True,
    "nonmatching_untracked_files_always_in_final_diff": True,
    "require_inventory": True,
    "require_hash_exclusion_alignment": True,
}


class WorkspaceArtifactPolicyError(ValueError):
    pass


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_policy(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WorkspaceArtifactPolicyError(
            f"Workspace artifact policy is not valid JSON: {error}"
        ) from error
    issues = validate_policy(value)
    if issues:
        raise WorkspaceArtifactPolicyError("; ".join(issues))
    return value


def validate_policy(value: Any) -> list[str]:
    issues: list[str] = []
    if not isinstance(value, dict) or set(value) != POLICY_KEYS:
        return ["workspace artifact policy fields do not match the v1 contract"]
    if value["schema_version"] != "1.0.0":
        issues.append("workspace artifact policy schema_version must be 1.0.0")
    if value["status"] not in {"CANDIDATE", "FROZEN"}:
        issues.append("workspace artifact policy status must be CANDIDATE or FROZEN")
    if value["policy_id"] != "tsb-incidental-workspace-artifacts-v1":
        issues.append("workspace artifact policy_id is invalid")
    if value["effective_scope"] != "future_runs_prepared_with_policy_snapshot":
        issues.append("workspace artifact policy effective_scope is invalid")
    if not isinstance(value["historical_run_rule"], str) or not value[
        "historical_run_rule"
    ].strip():
        issues.append("historical_run_rule must be a non-empty string")
    if value["controls"] != CONTROL_VALUES:
        issues.append("workspace artifact policy controls must match the v1 controls")
    classifications = value["classifications"]
    if not isinstance(classifications, list) or not classifications:
        issues.append("workspace artifact policy requires classifications")
        return issues
    ids: list[str] = []
    for index, item in enumerate(classifications):
        label = f"classifications[{index}]"
        if not isinstance(item, dict) or set(item) != CLASSIFICATION_KEYS:
            issues.append(f"{label} fields do not match the v1 contract")
            continue
        item_id = item["id"]
        if not isinstance(item_id, str) or not item_id:
            issues.append(f"{label}.id must be a non-empty string")
        else:
            ids.append(item_id)
        if item["untracked_only"] is not True:
            issues.append(f"{label}.untracked_only must be true")
        if item["treatment"] != "inventory_and_exclude_from_final_diff":
            issues.append(f"{label}.treatment is invalid")
        for field in ("directory_names", "suffixes"):
            entries = item[field]
            if not isinstance(entries, list) or any(
                not isinstance(entry, str) or not entry for entry in entries
            ):
                issues.append(f"{label}.{field} must contain non-empty strings")
            elif len(entries) != len(set(entries)):
                issues.append(f"{label}.{field} contains duplicates")
        for name in item.get("directory_names", []):
            if "/" in name or "\\" in name or name in {".", "..", ".git"}:
                issues.append(f"{label}.directory_names contains an unsafe name")
        for suffix in item.get("suffixes", []):
            if not suffix.startswith(".") or "/" in suffix or "\\" in suffix:
                issues.append(f"{label}.suffixes contains an unsafe suffix")
    if len(ids) != len(set(ids)):
        issues.append("workspace artifact classification IDs must be unique")
    return issues


def policy_patterns(policy: dict[str, Any]) -> tuple[set[str], set[str]]:
    directories: set[str] = set()
    suffixes: set[str] = set()
    for item in policy["classifications"]:
        directories.update(item["directory_names"])
        suffixes.update(item["suffixes"])
    return directories, suffixes


def validate_hash_exclusion_alignment(
    policy: dict[str, Any], fixture_manifest: dict[str, Any]
) -> list[str]:
    policy_directories, policy_suffixes = policy_patterns(policy)
    hash_directories, hash_suffixes = hash_exclusions(fixture_manifest)
    issues: list[str] = []
    missing_directories = sorted(policy_directories - hash_directories)
    missing_suffixes = sorted(policy_suffixes - hash_suffixes)
    if missing_directories:
        issues.append(
            "workspace artifact directories are not excluded from the task hash: "
            + ", ".join(missing_directories)
        )
    if missing_suffixes:
        issues.append(
            "workspace artifact suffixes are not excluded from the task hash: "
            + ", ".join(missing_suffixes)
        )
    return issues


def classification_for_path(
    relative_path: Path, policy: dict[str, Any]
) -> str | None:
    for item in policy["classifications"]:
        if set(relative_path.parts).intersection(item["directory_names"]):
            return item["id"]
        if relative_path.suffix in item["suffixes"]:
            return item["id"]
    return None


def _tracked_paths(workspace: Path) -> set[str]:
    completed = subprocess.run(
        [find_git(), "ls-files", "-z"],
        cwd=workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")
        raise WorkspaceArtifactPolicyError(f"Cannot list tracked files: {detail}")
    return {
        item.decode("utf-8", errors="surrogateescape")
        for item in completed.stdout.split(b"\0")
        if item
    }


def inventory_incidental_artifacts(
    workspace: Path, policy: dict[str, Any]
) -> list[dict[str, Any]]:
    root = workspace.resolve()
    tracked = _tracked_paths(root)
    entries: list[dict[str, Any]] = []
    for path in sorted(
        (candidate for candidate in root.rglob("*") if candidate.is_file()),
        key=lambda candidate: candidate.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            continue
        relative_text = relative.as_posix()
        if relative_text in tracked:
            continue
        classification = classification_for_path(relative, policy)
        if classification is None:
            continue
        entries.append(
            {
                "path": relative_text,
                "classification": classification,
                "size_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return entries


def build_inventory(
    *,
    policy_path: Path,
    policy: dict[str, Any],
    workspace: Path,
    status: str,
) -> dict[str, Any]:
    if status not in {"not_scanned", "completed"}:
        raise WorkspaceArtifactPolicyError("Unsupported incidental inventory status")
    entries = (
        inventory_incidental_artifacts(workspace, policy)
        if status == "completed"
        else []
    )
    return {
        "schema_version": "1.0.0",
        "status": status,
        "policy_id": policy["policy_id"],
        "policy_sha256": file_sha256(policy_path),
        "entries": entries,
    }


def validate_inventory(
    value: Any,
    *,
    policy_path: Path,
    policy: dict[str, Any],
    workspace: Path | None,
    require_completed: bool,
) -> list[str]:
    issues: list[str] = []
    expected_keys = {
        "schema_version",
        "status",
        "policy_id",
        "policy_sha256",
        "entries",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        return ["incidental_artifacts.json fields do not match the v1 contract"]
    if value["schema_version"] != "1.0.0":
        issues.append("incidental artifact schema_version must be 1.0.0")
    expected_status = "completed" if require_completed else "not_scanned"
    if value["status"] != expected_status:
        issues.append(f"incidental artifact status must be {expected_status}")
    if value["policy_id"] != policy["policy_id"]:
        issues.append("incidental artifact policy_id disagrees with its snapshot")
    if value["policy_sha256"] != file_sha256(policy_path):
        issues.append("incidental artifact policy_sha256 disagrees with its snapshot")
    entries = value["entries"]
    if not isinstance(entries, list):
        issues.append("incidental artifact entries must be an array")
        return issues
    expected_entry_keys = {"path", "classification", "size_bytes", "sha256"}
    paths: list[str] = []
    for index, entry in enumerate(entries):
        label = f"incidental artifact entries[{index}]"
        if not isinstance(entry, dict) or set(entry) != expected_entry_keys:
            issues.append(f"{label} fields do not match the v1 contract")
            continue
        path_text = entry["path"]
        if (
            not isinstance(path_text, str)
            or not path_text
            or "\\" in path_text
            or path_text.startswith("/")
            or ".." in Path(path_text).parts
        ):
            issues.append(f"{label}.path is unsafe")
        else:
            paths.append(path_text)
            expected_classification = classification_for_path(Path(path_text), policy)
            if entry["classification"] != expected_classification:
                issues.append(
                    f"{label}.classification disagrees with the policy path match"
                )
        if not isinstance(entry["classification"], str):
            issues.append(f"{label}.classification must be a string")
        if not isinstance(entry["size_bytes"], int) or entry["size_bytes"] < 0:
            issues.append(f"{label}.size_bytes must be a non-negative integer")
        sha256 = entry["sha256"]
        if (
            not isinstance(sha256, str)
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
        ):
            issues.append(f"{label}.sha256 must be a lowercase SHA-256 digest")
    if paths != sorted(set(paths)):
        issues.append("incidental artifact paths must be unique and sorted")
    if workspace is not None and require_completed:
        try:
            observed = inventory_incidental_artifacts(workspace, policy)
        except WorkspaceArtifactPolicyError as error:
            issues.append(str(error))
        else:
            if entries != observed:
                issues.append("incidental artifact inventory disagrees with the workspace")
    elif not require_completed and entries:
        issues.append("not_scanned incidental artifact inventory must have no entries")
    return issues


def install_git_excludes(workspace: Path, policy: dict[str, Any]) -> None:
    directories, suffixes = policy_patterns(policy)
    lines = [
        "# TSB incidental workspace artifacts; evidence remains in incidental_artifacts.json"
    ]
    lines.extend(f"{name}/" for name in sorted(directories))
    lines.extend(f"*{suffix}" for suffix in sorted(suffixes))
    exclude_path = workspace / ".git" / "info" / "exclude"
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
    block = "\n".join(lines) + "\n"
    if block not in existing:
        separator = "" if not existing or existing.endswith("\n") else "\n"
        exclude_path.write_text(existing + separator + block, encoding="utf-8")
