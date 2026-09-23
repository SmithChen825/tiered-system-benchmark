from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .common import REPOSITORY_ROOT, write_json
except ImportError:  # Supports direct script execution.
    from common import REPOSITORY_ROOT, write_json  # type: ignore


SCHEMA_VERSION = "1.0.0"
ZERO_SHA256 = "0" * 64
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
FREEZE_SCOPES = {"pilot_candidate", "main_experiment"}
PILOT_COMPONENT_PATHS = {
    "native_ide_configuration": {"benchmark/config/native_ide_freeze.json"},
    "api_transport_configuration": {"benchmark/config/api_transport_configuration.json"},
    "common_system_prompt": {"benchmark/config/common_system_prompt.txt"},
    "tool_action_schema": {"benchmark/config/tool_action_schema.json"},
    "context_policy": {"benchmark/config/context_policy.json"},
    "execution_limits": {"benchmark/config/execution_limits.json"},
    "task_set": {"benchmark/config/task_set.json"},
    "evaluation_contract": {"benchmark/config/evaluation_bundle.json"},
    "run_schedule": {"benchmark/config/run_schedule.json"},
    "analysis_plan": {"benchmark/config/pilot_analysis_plan.json"},
}
MAIN_COMPONENT_PATHS = {
    "native_ide_configuration": {"benchmark/config/native_ide_freeze.json"},
    "api_transport_configuration": {"benchmark/config/api_transport_configuration.main.json"},
    "common_system_prompt": {"benchmark/config/common_system_prompt.main.txt"},
    "tool_action_schema": {"benchmark/config/tool_action_schema.json"},
    "context_policy": {"benchmark/config/context_policy.main.json"},
    "execution_limits": {"benchmark/config/execution_limits.main.json"},
    "task_set": {"benchmark/config/task_set.main.json"},
    "evaluation_contract": {"benchmark/config/evaluation_bundle.main.json"},
    "run_schedule": {"benchmark/config/run_schedule.main.json"},
    "analysis_plan": {"benchmark/config/analysis_plan.main.json"},
}
REQUIRED_COMPONENTS = {
    "native_ide_configuration",
    "api_transport_configuration",
    "common_system_prompt",
    "tool_action_schema",
    "context_policy",
    "execution_limits",
    "task_set",
    "evaluation_contract",
    "run_schedule",
    "analysis_plan",
}
HASH_POLICY = {
    "file_hash": "sha256_raw_bytes",
    "configuration_set_hash": "sha256_component_path_digest_size_nul_v1",
    "manifest_hash": "sha256_canonical_json_without_manifest_sha256_v1",
    "amendment_chain_hash": "sha256_canonical_json_without_entry_sha256_v1",
}
MANIFEST_FIELDS = {
    "schema_version",
    "freeze_status",
    "freeze_scope",
    "freeze_id",
    "frozen_at",
    "timezone",
    "supersedes_freeze_id",
    "hash_policy",
    "required_components",
    "configuration_items",
    "configuration_set_sha256",
    "amendment_log",
    "manifest_sha256",
    "notes",
}
ITEM_FIELDS = {"component_id", "path", "sha256", "size_bytes"}
LOG_FIELDS = {
    "schema_version",
    "log_id",
    "base_freeze_id",
    "base_manifest_sha256",
    "hash_algorithm",
    "entries",
    "head_sha256",
}
ENTRY_FIELDS = {
    "amendment_id",
    "recorded_at",
    "effective_at",
    "trigger",
    "change_summary",
    "rationale",
    "changed_components",
    "changed_files",
    "affected_run_ids",
    "resolution_status",
    "run_disposition",
    "replacement_freeze_id",
    "replacement_manifest_sha256",
    "authorization_reference",
    "previous_entry_sha256",
    "entry_sha256",
}
DRAFT_FIELDS = ENTRY_FIELDS - {"previous_entry_sha256", "entry_sha256"}
RESOLVED_DISPOSITIONS = {
    "no_runs_affected",
    "invalidate_and_rerun",
    "retain_as_separate_configuration",
    "terminate_collection",
}


class FreezeError(RuntimeError):
    pass


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_sha256(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload.pop("manifest_sha256", None)
    return canonical_json_sha256(payload)


def amendment_entry_sha256(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    payload.pop("entry_sha256", None)
    return canonical_json_sha256(payload)


def configuration_set_sha256(items: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    ordered = sorted(items, key=lambda item: (item["component_id"], item["path"]))
    for item in ordered:
        sha256 = item.get("sha256")
        size_bytes = item.get("size_bytes")
        if SHA256_PATTERN.fullmatch(sha256 or "") is None:
            raise FreezeError(f"Missing or invalid hash for {item.get('path')!r}")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise FreezeError(f"Missing or invalid size for {item.get('path')!r}")
        for part in (
            item["component_id"],
            item["path"],
            sha256,
            str(size_bytes),
        ):
            digest.update(part.encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def _is_nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _is_datetime(value: Any) -> bool:
    if not _is_nonempty_text(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _resolve_repository_path(
    repository_root: Path, raw_path: Any
) -> tuple[Path | None, str | None]:
    if not _is_nonempty_text(raw_path):
        return None, "must be a non-empty repository-relative POSIX path"
    if "\\" in raw_path:
        return None, "must use POSIX separators"
    relative = Path(raw_path)
    if relative.is_absolute() or raw_path.startswith("/") or ".." in relative.parts:
        return None, "must stay within the repository"
    root = repository_root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None, "must stay within the repository"
    if relative.as_posix() != raw_path:
        return None, "must be normalized as a repository-relative POSIX path"
    return resolved, None


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def validate_component_semantics(
    manifest: dict[str, Any], *, repository_root: Path = REPOSITORY_ROOT
) -> list[str]:
    """Validate the meaning of every frozen component, not only its file hash."""

    issues: list[str] = []
    scope = manifest.get("freeze_scope")
    expected = (
        PILOT_COMPONENT_PATHS
        if scope == "pilot_candidate"
        else MAIN_COMPONENT_PATHS
        if scope == "main_experiment"
        else None
    )
    if expected is None:
        return ["component semantics require a recognized freeze_scope"]

    items = manifest.get("configuration_items")
    if not isinstance(items, list):
        return ["component semantics require configuration_items"]
    observed: dict[str, set[str]] = {component: set() for component in REQUIRED_COMPONENTS}
    for item in items:
        if not isinstance(item, dict):
            continue
        component = item.get("component_id")
        path = item.get("path")
        if component in observed and isinstance(path, str):
            observed[component].add(path)
    for component in sorted(REQUIRED_COMPONENTS):
        if observed[component] != expected[component]:
            issues.append(
                f"{component} paths must equal {sorted(expected[component])}, "
                f"observed {sorted(observed[component])}"
            )
    if issues:
        return issues

    resolved: dict[str, Path] = {}
    for component, paths in expected.items():
        raw_path = next(iter(paths))
        path, path_issue = _resolve_repository_path(repository_root, raw_path)
        if path_issue or path is None or not path.is_file():
            issues.append(f"{component} semantic source is unavailable: {raw_path}")
        else:
            resolved[component] = path
    if issues:
        return issues

    try:
        from .api_transport_configuration import validate_api_transport_configuration
        from .common_agent_configuration import (
            validate_common_system_prompt,
            validate_tool_action_schema,
        )
        from .experiment_design_configuration import (
            validate_analysis_plan,
            validate_schedule,
        )
        from .native_ide_freeze_validator import validate_native_ide_freeze
        from .pilot_analysis_configuration import validate_pilot_analysis_plan
        from .runtime_policy_configuration import (
            validate_context_policy,
            validate_execution_limits,
        )
        from .task_evaluation_configuration import (
            validate_evaluation_bundle,
            validate_task_set,
        )
    except ImportError as error:
        return [f"component semantic validator import failed: {error}"]

    json_values: dict[str, dict[str, Any]] = {}
    for component, path in resolved.items():
        if component == "common_system_prompt":
            continue
        try:
            json_values[component] = _load_json_object(path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            issues.append(f"{component} is invalid JSON: {error}")
    if issues:
        return issues

    try:
        prompt = resolved["common_system_prompt"].read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        issues.append(f"common_system_prompt could not be read: {error}")
    else:
        issues.extend(
            "common_system_prompt: " + issue
            for issue in validate_common_system_prompt(
                prompt,
                api_action_limit=30 if scope == "main_experiment" else 15,
            )
        )
    issues.extend(
        "native_ide_configuration: " + issue
        for issue in validate_native_ide_freeze(
            json_values["native_ide_configuration"],
            require_frozen=True,
            repository_root=repository_root,
            verify_files=True,
        )
    )
    issues.extend(
        "api_transport_configuration: " + issue
        for issue in validate_api_transport_configuration(
            json_values["api_transport_configuration"],
            require_frozen=True,
            repository_root=repository_root,
        )
    )
    issues.extend(
        "tool_action_schema: " + issue
        for issue in validate_tool_action_schema(
            json_values["tool_action_schema"], require_frozen=True
        )
    )
    issues.extend(
        "context_policy: " + issue
        for issue in validate_context_policy(
            json_values["context_policy"], require_frozen=True
        )
    )
    issues.extend(
        "execution_limits: " + issue
        for issue in validate_execution_limits(
            json_values["execution_limits"], require_frozen=True
        )
    )
    task_set = json_values["task_set"]
    issues.extend(
        "task_set: " + issue
        for issue in validate_task_set(
            task_set, repository_root=repository_root, require_frozen=True
        )
    )
    issues.extend(
        "evaluation_contract: " + issue
        for issue in validate_evaluation_bundle(
            json_values["evaluation_contract"],
            repository_root=repository_root,
            task_set=task_set,
            require_frozen=True,
        )
    )
    issues.extend(
        "run_schedule: " + issue
        for issue in validate_schedule(
            json_values["run_schedule"],
            repository_root=repository_root,
            task_set=task_set,
            require_frozen=True,
        )
    )
    analysis = json_values["analysis_plan"]
    if scope == "pilot_candidate":
        issues.extend(
            "analysis_plan: " + issue
            for issue in validate_pilot_analysis_plan(analysis, require_frozen=True)
        )
    else:
        issues.extend(
            "analysis_plan: " + issue
            for issue in validate_analysis_plan(
                analysis, repository_root=repository_root, require_frozen=True
            )
        )
    return issues


def validate_experiment_freeze(
    value: dict[str, Any],
    *,
    repository_root: Path = REPOSITORY_ROOT,
    require_frozen: bool = True,
    verify_files: bool = True,
    verify_component_semantics: bool = True,
) -> list[str]:
    issues: list[str] = []
    missing = sorted(MANIFEST_FIELDS - set(value))
    unexpected = sorted(set(value) - MANIFEST_FIELDS)
    if missing:
        issues.append("Missing top-level fields: " + ", ".join(missing))
    if unexpected:
        issues.append("Unexpected top-level fields: " + ", ".join(unexpected))
    if missing:
        return issues

    if value["schema_version"] != SCHEMA_VERSION:
        issues.append(f"schema_version must be {SCHEMA_VERSION}")
    if value["freeze_status"] not in {"UNFROZEN", "FROZEN"}:
        issues.append("freeze_status must be UNFROZEN or FROZEN")
    if require_frozen and value["freeze_status"] != "FROZEN":
        issues.append("freeze_status must be FROZEN before pilot or main execution")
    if value["freeze_scope"] not in FREEZE_SCOPES:
        issues.append(f"freeze_scope must be one of {sorted(FREEZE_SCOPES)}")
    if value["timezone"] != "Australia/Sydney":
        issues.append("timezone must be Australia/Sydney")
    if value["hash_policy"] != HASH_POLICY:
        issues.append("hash_policy must equal the version 1.0.0 freeze hash policy")
    if value["required_components"] != sorted(REQUIRED_COMPONENTS):
        issues.append("required_components must contain the exact version 1.0.0 set")

    frozen = value["freeze_status"] == "FROZEN"
    if frozen:
        if not _is_nonempty_text(value["freeze_id"]):
            issues.append("freeze_id must be non-empty when frozen")
        if not _is_datetime(value["frozen_at"]):
            issues.append("frozen_at must be an ISO 8601 timestamp with an offset")
    else:
        if value["freeze_id"] is not None:
            issues.append("freeze_id must be null while UNFROZEN")
        if value["frozen_at"] is not None:
            issues.append("frozen_at must be null while UNFROZEN")
    if value["supersedes_freeze_id"] is not None and not _is_nonempty_text(
        value["supersedes_freeze_id"]
    ):
        issues.append("supersedes_freeze_id must be null or non-empty")

    amendment_log = value["amendment_log"]
    if not isinstance(amendment_log, dict) or set(amendment_log) != {
        "path",
        "chain_algorithm",
    }:
        issues.append("amendment_log must contain only path and chain_algorithm")
    else:
        _, path_issue = _resolve_repository_path(
            repository_root, amendment_log.get("path")
        )
        if path_issue:
            issues.append(f"amendment_log.path {path_issue}")
        if amendment_log.get("chain_algorithm") != HASH_POLICY["amendment_chain_hash"]:
            issues.append("amendment_log.chain_algorithm does not match hash_policy")

    items = value["configuration_items"]
    if not isinstance(items, list) or not items:
        issues.append("configuration_items must be a non-empty list")
        return issues
    paths: set[str] = set()
    represented_components: set[str] = set()
    complete_for_aggregate = True
    structurally_valid_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        prefix = f"configuration_items[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{prefix} must be an object")
            complete_for_aggregate = False
            continue
        if set(item) != ITEM_FIELDS:
            issues.append(f"{prefix} must contain exactly {sorted(ITEM_FIELDS)}")
            complete_for_aggregate = False
            continue
        component_id = item["component_id"]
        if component_id not in REQUIRED_COMPONENTS:
            issues.append(f"{prefix}.component_id is not a required component")
        else:
            represented_components.add(component_id)
        raw_path = item["path"]
        resolved, path_issue = _resolve_repository_path(repository_root, raw_path)
        if path_issue:
            issues.append(f"{prefix}.path {path_issue}")
            complete_for_aggregate = False
        elif raw_path in paths:
            issues.append(f"{prefix}.path duplicates {raw_path}")
        else:
            paths.add(raw_path)

        sha256 = item["sha256"]
        size_bytes = item["size_bytes"]
        hash_present = sha256 is not None
        size_present = size_bytes is not None
        if hash_present != size_present:
            issues.append(f"{prefix}.sha256 and size_bytes must both be set or null")
        if hash_present and not _is_sha256(sha256):
            issues.append(f"{prefix}.sha256 must be a lowercase SHA-256 value")
        if size_present and (
            not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes < 0
        ):
            issues.append(f"{prefix}.size_bytes must be a non-negative integer")
        if not hash_present or not size_present:
            complete_for_aggregate = False
            if frozen:
                issues.append(f"{prefix} must be hashed when frozen")

        if resolved is not None and verify_files and (frozen or hash_present):
            if not resolved.is_file():
                issues.append(f"{prefix}.path does not name an existing regular file")
            elif _is_sha256(sha256) and isinstance(size_bytes, int):
                observed_size = resolved.stat().st_size
                observed_hash = file_sha256(resolved)
                if observed_size != size_bytes:
                    issues.append(
                        f"{prefix}.size_bytes mismatch: expected {size_bytes}, "
                        f"observed {observed_size}"
                    )
                if observed_hash != sha256:
                    issues.append(
                        f"{prefix}.sha256 mismatch: expected {sha256}, "
                        f"observed {observed_hash}"
                    )
        structurally_valid_items.append(item)

    missing_components = sorted(REQUIRED_COMPONENTS - represented_components)
    if missing_components:
        issues.append("configuration_items omit components: " + ", ".join(missing_components))

    stored_set_hash = value["configuration_set_sha256"]
    if stored_set_hash is not None and not _is_sha256(stored_set_hash):
        issues.append("configuration_set_sha256 must be null or a lowercase SHA-256")
    if complete_for_aggregate and len(structurally_valid_items) == len(items):
        try:
            observed_set_hash = configuration_set_sha256(structurally_valid_items)
        except (FreezeError, KeyError):
            observed_set_hash = None
        if observed_set_hash is not None and stored_set_hash != observed_set_hash:
            issues.append(
                "configuration_set_sha256 mismatch: "
                f"expected {stored_set_hash}, observed {observed_set_hash}"
            )
    elif frozen:
        issues.append("configuration_set_sha256 cannot be established from incomplete items")

    stored_manifest_hash = value["manifest_sha256"]
    if stored_manifest_hash is not None and not _is_sha256(stored_manifest_hash):
        issues.append("manifest_sha256 must be null or a lowercase SHA-256")
    if stored_manifest_hash is not None:
        observed_manifest_hash = manifest_sha256(value)
        if stored_manifest_hash != observed_manifest_hash:
            issues.append(
                "manifest_sha256 mismatch: "
                f"expected {stored_manifest_hash}, observed {observed_manifest_hash}"
            )
    elif frozen:
        issues.append("manifest_sha256 must be recorded when frozen")
    if frozen and verify_component_semantics:
        issues.extend(
            "component_semantics: " + issue
            for issue in validate_component_semantics(
                value, repository_root=repository_root
            )
        )
    return issues


def validate_amendment_log(
    value: dict[str, Any],
    *,
    expected_freeze_id: str | None = None,
    expected_manifest_sha256: str | None = None,
    require_bound: bool = True,
    require_resolved: bool = True,
) -> list[str]:
    issues: list[str] = []
    missing = sorted(LOG_FIELDS - set(value))
    unexpected = sorted(set(value) - LOG_FIELDS)
    if missing:
        issues.append("Missing amendment-log fields: " + ", ".join(missing))
    if unexpected:
        issues.append("Unexpected amendment-log fields: " + ", ".join(unexpected))
    if missing:
        return issues
    if value["schema_version"] != SCHEMA_VERSION:
        issues.append(f"schema_version must be {SCHEMA_VERSION}")
    if value["hash_algorithm"] != HASH_POLICY["amendment_chain_hash"]:
        issues.append("hash_algorithm does not match the version 1.0.0 chain policy")
    if require_bound:
        if not _is_nonempty_text(value["log_id"]):
            issues.append("log_id must be non-empty")
        if not _is_nonempty_text(value["base_freeze_id"]):
            issues.append("base_freeze_id must be non-empty")
        if not _is_sha256(value["base_manifest_sha256"]):
            issues.append("base_manifest_sha256 must be a lowercase SHA-256")
    if expected_freeze_id is not None and value["base_freeze_id"] != expected_freeze_id:
        issues.append("base_freeze_id does not match the freeze manifest")
    if (
        expected_manifest_sha256 is not None
        and value["base_manifest_sha256"] != expected_manifest_sha256
    ):
        issues.append("base_manifest_sha256 does not match the freeze manifest")

    entries = value["entries"]
    if not isinstance(entries, list):
        return issues + ["entries must be a list"]
    previous = ZERO_SHA256
    amendment_ids: set[str] = set()
    for index, entry in enumerate(entries):
        prefix = f"entries[{index}]"
        if not isinstance(entry, dict):
            issues.append(f"{prefix} must be an object")
            continue
        if set(entry) != ENTRY_FIELDS:
            issues.append(f"{prefix} must contain exactly {sorted(ENTRY_FIELDS)}")
            continue
        amendment_id = entry["amendment_id"]
        if not _is_nonempty_text(amendment_id):
            issues.append(f"{prefix}.amendment_id must be non-empty")
        elif amendment_id in amendment_ids:
            issues.append(f"{prefix}.amendment_id is duplicated")
        else:
            amendment_ids.add(amendment_id)
        for field in (
            "recorded_at",
            "effective_at",
        ):
            if not _is_datetime(entry[field]):
                issues.append(f"{prefix}.{field} must be an ISO 8601 timestamp with an offset")
        for field in (
            "trigger",
            "change_summary",
            "rationale",
            "authorization_reference",
        ):
            if not _is_nonempty_text(entry[field]):
                issues.append(f"{prefix}.{field} must be non-empty")
        for field in ("changed_components", "changed_files", "affected_run_ids"):
            field_value = entry[field]
            if not isinstance(field_value, list) or any(
                not _is_nonempty_text(item) for item in field_value
            ):
                issues.append(f"{prefix}.{field} must be a list of non-empty strings")
        components = entry["changed_components"]
        if isinstance(components, list):
            unknown = sorted(set(components) - REQUIRED_COMPONENTS)
            if unknown:
                issues.append(f"{prefix}.changed_components contains unknown values: {unknown}")
            if not components:
                issues.append(f"{prefix}.changed_components must not be empty")
        status = entry["resolution_status"]
        disposition = entry["run_disposition"]
        replacement_id = entry["replacement_freeze_id"]
        replacement_hash = entry["replacement_manifest_sha256"]
        if status == "pending":
            if disposition != "pending_review":
                issues.append(f"{prefix}.run_disposition must be pending_review while pending")
            if require_resolved:
                issues.append(f"{prefix} is unresolved and blocks experiment execution")
        elif status == "resolved":
            if disposition not in RESOLVED_DISPOSITIONS:
                issues.append(
                    f"{prefix}.run_disposition must be one of {sorted(RESOLVED_DISPOSITIONS)}"
                )
            if not _is_nonempty_text(replacement_id) or not _is_sha256(replacement_hash):
                issues.append(
                    f"{prefix} must link a replacement freeze ID and manifest hash when resolved"
                )
        else:
            issues.append(f"{prefix}.resolution_status must be pending or resolved")
        if entry["previous_entry_sha256"] != previous:
            issues.append(f"{prefix}.previous_entry_sha256 breaks the amendment chain")
        observed_entry_hash = amendment_entry_sha256(entry)
        if entry["entry_sha256"] != observed_entry_hash:
            issues.append(f"{prefix}.entry_sha256 does not match its canonical content")
        previous = observed_entry_hash
    expected_head = previous if entries else ZERO_SHA256
    if value["head_sha256"] != expected_head:
        issues.append("head_sha256 does not match the final amendment entry")
    return issues


def snapshot_manifest(
    value: dict[str, Any], *, repository_root: Path = REPOSITORY_ROOT
) -> tuple[dict[str, Any], list[str]]:
    if value.get("freeze_status") == "FROZEN":
        raise FreezeError("Refusing to refresh hashes in a FROZEN manifest")
    result = copy.deepcopy(value)
    missing_paths: list[str] = []
    for item in result.get("configuration_items", []):
        if not isinstance(item, dict):
            continue
        resolved, path_issue = _resolve_repository_path(repository_root, item.get("path"))
        if path_issue or resolved is None or not resolved.is_file():
            item["sha256"] = None
            item["size_bytes"] = None
            missing_paths.append(str(item.get("path")))
            continue
        item["sha256"] = file_sha256(resolved)
        item["size_bytes"] = resolved.stat().st_size
    try:
        result["configuration_set_sha256"] = configuration_set_sha256(
            result["configuration_items"]
        )
    except (FreezeError, KeyError, TypeError):
        result["configuration_set_sha256"] = None
    result["manifest_sha256"] = manifest_sha256(result)
    return result, missing_paths


def append_amendment(
    log: dict[str, Any], draft: dict[str, Any]
) -> dict[str, Any]:
    base_issues = validate_amendment_log(log, require_resolved=False)
    if base_issues:
        raise FreezeError("Cannot append to invalid log: " + "; ".join(base_issues))
    missing = sorted(DRAFT_FIELDS - set(draft))
    unexpected = sorted(set(draft) - DRAFT_FIELDS)
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise FreezeError("Invalid amendment draft: " + "; ".join(details))
    existing_ids = {entry["amendment_id"] for entry in log["entries"]}
    if draft["amendment_id"] in existing_ids:
        raise FreezeError(f"Duplicate amendment_id: {draft['amendment_id']}")
    result = copy.deepcopy(log)
    entry = copy.deepcopy(draft)
    entry["previous_entry_sha256"] = result["head_sha256"]
    entry["entry_sha256"] = amendment_entry_sha256(entry)
    result["entries"].append(entry)
    result["head_sha256"] = entry["entry_sha256"]
    issues = validate_amendment_log(result, require_resolved=False)
    if issues:
        raise FreezeError("Invalid amendment: " + "; ".join(issues))
    return result


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FreezeError(f"Could not read JSON object {path}: {error}") from error
    if not isinstance(value, dict):
        raise FreezeError(f"Expected a JSON object in {path}")
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    write_json(temporary, value)
    temporary.replace(path)


def _print_issues(issues: list[str]) -> None:
    for issue in issues:
        print(f"ERROR: {issue}")


def _load_linked_log(
    manifest: dict[str, Any], repository_root: Path
) -> tuple[dict[str, Any] | None, list[str]]:
    amendment = manifest.get("amendment_log")
    if not isinstance(amendment, dict):
        return None, ["Cannot resolve amendment_log from the freeze manifest"]
    path, path_issue = _resolve_repository_path(repository_root, amendment.get("path"))
    if path_issue or path is None:
        return None, [f"amendment_log.path {path_issue}"]
    if not path.is_file():
        return None, [f"amendment log does not exist: {amendment.get('path')}"]
    try:
        return _read_object(path), []
    except FreezeError as error:
        return None, [str(error)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Snapshot, seal, and verify the TSB experiment freeze."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("manifest", type=Path)
    validate_parser.add_argument("--allow-unfrozen", action="store_true")
    validate_parser.add_argument("--skip-file-verification", action="store_true")

    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("manifest", type=Path)
    snapshot_parser.add_argument("--allow-incomplete", action="store_true")

    seal_parser = subparsers.add_parser("seal")
    seal_parser.add_argument("manifest", type=Path)
    seal_parser.add_argument("--freeze-id", required=True)
    seal_parser.add_argument("--frozen-at", required=True)
    seal_parser.add_argument("--scope", choices=sorted(FREEZE_SCOPES), required=True)
    seal_parser.add_argument("--supersedes-freeze-id")

    verify_parser = subparsers.add_parser("verify-amendments")
    verify_parser.add_argument("log", type=Path)
    verify_parser.add_argument("--manifest", type=Path)
    verify_parser.add_argument("--allow-unbound", action="store_true")
    verify_parser.add_argument("--allow-pending", action="store_true")

    append_parser = subparsers.add_parser("append-amendment")
    append_parser.add_argument("log", type=Path)
    append_parser.add_argument("draft", type=Path)

    arguments = parser.parse_args()
    repository_root = REPOSITORY_ROOT
    try:
        if arguments.command == "snapshot":
            value = _read_object(arguments.manifest)
            result, missing_paths = snapshot_manifest(
                value, repository_root=repository_root
            )
            _write_json_atomic(arguments.manifest, result)
            print(f"manifest_sha256={result['manifest_sha256']}")
            if missing_paths:
                for path in missing_paths:
                    print(f"MISSING: {path}")
                if not arguments.allow_incomplete:
                    raise SystemExit(1)
            return

        if arguments.command == "seal":
            value = _read_object(arguments.manifest)
            result, missing_paths = snapshot_manifest(
                value, repository_root=repository_root
            )
            if missing_paths:
                raise FreezeError(
                    "Cannot seal with missing configuration files: "
                    + ", ".join(missing_paths)
                )
            result["freeze_status"] = "FROZEN"
            result["freeze_scope"] = arguments.scope
            result["freeze_id"] = arguments.freeze_id
            result["frozen_at"] = arguments.frozen_at
            result["supersedes_freeze_id"] = arguments.supersedes_freeze_id
            result["configuration_set_sha256"] = configuration_set_sha256(
                result["configuration_items"]
            )
            result["manifest_sha256"] = manifest_sha256(result)
            issues = validate_experiment_freeze(
                result, repository_root=repository_root
            )
            if issues:
                raise FreezeError("Cannot seal invalid manifest: " + "; ".join(issues))
            log_path, path_issue = _resolve_repository_path(
                repository_root, result["amendment_log"]["path"]
            )
            if path_issue or log_path is None:
                raise FreezeError(f"Invalid amendment log path: {path_issue}")
            if log_path.exists():
                log = _read_object(log_path)
                if log.get("entries") or log.get("base_freeze_id") is not None:
                    raise FreezeError("Refusing to overwrite a bound or non-empty amendment log")
            else:
                log = {
                    "schema_version": SCHEMA_VERSION,
                    "log_id": None,
                    "base_freeze_id": None,
                    "base_manifest_sha256": None,
                    "hash_algorithm": HASH_POLICY["amendment_chain_hash"],
                    "entries": [],
                    "head_sha256": ZERO_SHA256,
                }
            log["log_id"] = f"amendments-{arguments.freeze_id}"
            log["base_freeze_id"] = arguments.freeze_id
            log["base_manifest_sha256"] = result["manifest_sha256"]
            log_issues = validate_amendment_log(
                log,
                expected_freeze_id=arguments.freeze_id,
                expected_manifest_sha256=result["manifest_sha256"],
            )
            if log_issues:
                raise FreezeError("Cannot initialize amendment log: " + "; ".join(log_issues))
            _write_json_atomic(arguments.manifest, result)
            _write_json_atomic(log_path, log)
            print(f"freeze_id={arguments.freeze_id}")
            print(f"manifest_sha256={result['manifest_sha256']}")
            print(f"amendment_log={log_path}")
            return

        if arguments.command == "append-amendment":
            result = append_amendment(
                _read_object(arguments.log), _read_object(arguments.draft)
            )
            _write_json_atomic(arguments.log, result)
            print(f"head_sha256={result['head_sha256']}")
            return

        if arguments.command == "verify-amendments":
            log = _read_object(arguments.log)
            expected_id = None
            expected_hash = None
            if arguments.manifest:
                manifest = _read_object(arguments.manifest)
                expected_id = manifest.get("freeze_id")
                expected_hash = manifest.get("manifest_sha256")
            issues = validate_amendment_log(
                log,
                expected_freeze_id=expected_id,
                expected_manifest_sha256=expected_hash,
                require_bound=not arguments.allow_unbound,
                require_resolved=not arguments.allow_pending,
            )
            if issues:
                _print_issues(issues)
                raise SystemExit(1)
            print(f"valid={arguments.log.resolve()}")
            print(f"head_sha256={log['head_sha256']}")
            return

        manifest = _read_object(arguments.manifest)
        issues = validate_experiment_freeze(
            manifest,
            repository_root=repository_root,
            require_frozen=not arguments.allow_unfrozen,
            verify_files=not arguments.skip_file_verification,
        )
        if not arguments.allow_unfrozen and not issues:
            log, log_load_issues = _load_linked_log(manifest, repository_root)
            issues.extend(log_load_issues)
            if log is not None:
                issues.extend(
                    validate_amendment_log(
                        log,
                        expected_freeze_id=manifest["freeze_id"],
                        expected_manifest_sha256=manifest["manifest_sha256"],
                    )
                )
        if issues:
            _print_issues(issues)
            raise SystemExit(1)
        print(f"valid={arguments.manifest.resolve()}")
        if manifest.get("manifest_sha256"):
            print(f"manifest_sha256={manifest['manifest_sha256']}")
    except FreezeError as error:
        print(f"ERROR: {error}")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
