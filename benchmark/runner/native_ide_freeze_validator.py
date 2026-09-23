from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .common import REPOSITORY_ROOT
except ImportError:  # Supports direct script execution.
    from common import REPOSITORY_ROOT  # type: ignore


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{40}$")
SYSTEM_IDS = {"cursor", "devin"}
REQUIRED_CAPTURE_KEYS = {
    "version_evidence",
    "default_agent",
    "visible_settings",
    "account_tier",
    "default_agent_reopen1",
    "default_agent_reopen2",
}
PRODUCT_MANAGED_PUBLISHERS = {"cursor": {"anysphere"}, "devin": {"cognition"}}


def _is_nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_hash(value: Any, label: str, issues: list[str]) -> None:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        issues.append(f"{label} must be a lowercase SHA-256 value")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def system_configuration_sha256(system: dict[str, Any]) -> str:
    payload = {key: value for key, value in system.items() if key != "configuration_sha256"}
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_repository_path(
    raw_path: Any, *, repository_root: Path, label: str, issues: list[str]
) -> Path | None:
    if not _is_nonempty_text(raw_path) or "\\" in raw_path or raw_path.startswith("/"):
        issues.append(f"{label} must be a repository-relative POSIX path")
        return None
    relative = Path(raw_path)
    if ".." in relative.parts or relative.as_posix() != raw_path:
        issues.append(f"{label} must be normalized and stay within the repository")
        return None
    root = repository_root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        issues.append(f"{label} must stay within the repository")
        return None
    return resolved


def validate_native_ide_freeze(
    value: dict[str, Any],
    *,
    require_frozen: bool = True,
    repository_root: Path = REPOSITORY_ROOT,
    verify_files: bool = True,
) -> list[str]:
    issues: list[str] = []
    required_top = {
        "schema_version",
        "freeze_status",
        "freeze_id",
        "observed_at",
        "timezone",
        "profile_policy",
        "systems",
    }
    missing = sorted(required_top - set(value))
    if missing:
        return ["Missing top-level fields: " + ", ".join(missing)]
    if value["schema_version"] != "1.1.0":
        issues.append("schema_version must be 1.1.0")
    if value["freeze_status"] not in {"UNFROZEN", "FROZEN"}:
        issues.append("freeze_status must be UNFROZEN or FROZEN")
    if require_frozen and value["freeze_status"] != "FROZEN":
        issues.append("freeze_status must be FROZEN before pilot execution")
    if value["timezone"] != "Australia/Sydney":
        issues.append("timezone must be Australia/Sydney")
    observed_at = value["observed_at"]
    if observed_at is not None:
        if not _is_nonempty_text(observed_at):
            issues.append("observed_at must be null or an ISO 8601 timestamp")
        else:
            try:
                parsed_observed_at = datetime.fromisoformat(
                    observed_at.replace("Z", "+00:00")
                )
            except ValueError:
                issues.append("observed_at must be an ISO 8601 timestamp")
            else:
                if parsed_observed_at.tzinfo is None:
                    issues.append("observed_at must include a UTC offset")

    policy = value["profile_policy"]
    if not isinstance(policy, dict):
        issues.append("profile_policy must be an object")
    else:
        expected_policy = {
            "profile_type": "dedicated_clean",
            "reuse_everyday_profile": False,
            "settings_sync_enabled": False,
            "isolated_user_data": True,
            "isolated_extensions": True,
            "third_party_extensions_allowed": False,
            "product_managed_first_party_extensions_allowed": True,
            "manual_model_override_allowed": False,
        }
        for key, expected in expected_policy.items():
            if policy.get(key) != expected:
                issues.append(f"profile_policy.{key} must equal {expected!r}")

    systems = value["systems"]
    if not isinstance(systems, list):
        return issues + ["systems must be a list"]
    system_map = {
        item.get("system_id"): item for item in systems if isinstance(item, dict)
    }
    if set(system_map) != SYSTEM_IDS or len(systems) != 2:
        issues.append("systems must contain exactly one cursor and one devin record")
        return issues

    profile_paths: set[str] = set()
    for system_id in sorted(SYSTEM_IDS):
        system = system_map[system_id]
        prefix = f"systems.{system_id}"
        for field in (
            "cli_version",
            "architecture",
            "package_version",
            "executable_file_version",
            "profile_name",
            "user_data_dir",
            "extensions_dir",
        ):
            if not _is_nonempty_text(system.get(field)):
                issues.append(f"{prefix}.{field} must be non-empty")
        commit = system.get("cli_commit")
        if not isinstance(commit, str) or COMMIT_PATTERN.fullmatch(commit) is None:
            issues.append(f"{prefix}.cli_commit must be a lowercase 40-character commit")
        _validate_hash(system.get("executable_sha256"), f"{prefix}.executable_sha256", issues)
        extensions = system.get("extensions")
        if extensions != []:
            issues.append(
                f"{prefix}.extensions must be empty because it records third-party extensions"
            )
        managed_extensions = system.get("product_managed_extensions")
        if not isinstance(managed_extensions, list):
            issues.append(f"{prefix}.product_managed_extensions must be a list")
            managed_extensions = []
        managed_by_directory: dict[str, dict[str, Any]] = {}
        for index, extension in enumerate(managed_extensions):
            extension_prefix = f"{prefix}.product_managed_extensions[{index}]"
            if not isinstance(extension, dict):
                issues.append(f"{extension_prefix} must be an object")
                continue
            required_extension_fields = {
                "directory",
                "extension_id",
                "publisher",
                "version",
                "application_scoped",
                "package_sha256",
            }
            if set(extension) != required_extension_fields:
                issues.append(
                    f"{extension_prefix} must contain exactly "
                    f"{sorted(required_extension_fields)}"
                )
            for field in ("directory", "extension_id", "publisher", "version"):
                if not _is_nonempty_text(extension.get(field)):
                    issues.append(f"{extension_prefix}.{field} must be non-empty")
            if extension.get("application_scoped") is not True:
                issues.append(f"{extension_prefix}.application_scoped must be true")
            _validate_hash(
                extension.get("package_sha256"),
                f"{extension_prefix}.package_sha256",
                issues,
            )
            publisher = extension.get("publisher")
            if publisher not in PRODUCT_MANAGED_PUBLISHERS[system_id]:
                issues.append(
                    f"{extension_prefix}.publisher is not an allowed first-party publisher"
                )
            directory = extension.get("directory")
            if isinstance(directory, str):
                if directory in managed_by_directory:
                    issues.append(f"{extension_prefix}.directory must be unique")
                managed_by_directory[directory] = extension
        external_bindings = system.get("external_configuration_bindings")
        if not isinstance(external_bindings, list):
            issues.append(f"{prefix}.external_configuration_bindings must be a list")
            external_bindings = []
        for index, binding in enumerate(external_bindings):
            binding_prefix = f"{prefix}.external_configuration_bindings[{index}]"
            if not isinstance(binding, dict):
                issues.append(f"{binding_prefix} must be an object")
                continue
            for field in ("label", "path_redacted"):
                if not _is_nonempty_text(binding.get(field)):
                    issues.append(f"{binding_prefix}.{field} must be non-empty")
            path_redacted = binding.get("path_redacted")
            if isinstance(path_redacted, str) and re.search(
                r"[A-Za-z]:[/\\]|@", path_redacted
            ):
                issues.append(
                    f"{binding_prefix}.path_redacted must not contain an absolute path or account identifier"
                )
            _validate_hash(binding.get("sha256"), f"{binding_prefix}.sha256", issues)
            if not isinstance(binding.get("length_bytes"), int) or binding.get(
                "length_bytes"
            ) < 0:
                issues.append(f"{binding_prefix}.length_bytes must be a non-negative integer")
            top_level_keys = binding.get("top_level_keys")
            if not isinstance(top_level_keys, list) or not all(
                _is_nonempty_text(item) for item in top_level_keys
            ):
                issues.append(f"{binding_prefix}.top_level_keys must be a text list")
        for field in ("user_data_dir", "extensions_dir"):
            path = system.get(field)
            if isinstance(path, str):
                if path in profile_paths:
                    issues.append(f"{prefix}.{field} must be unique across systems")
                profile_paths.add(path)
                resolved = _resolve_repository_path(
                    path,
                    repository_root=repository_root,
                    label=f"{prefix}.{field}",
                    issues=issues,
                )
                if verify_files and require_frozen and resolved is not None:
                    if not resolved.is_dir():
                        issues.append(f"{prefix}.{field} must name an existing directory")
                    elif field == "extensions_dir":
                        extension_directories = {
                            child.name: child
                            for child in resolved.iterdir()
                            if child.is_dir()
                        }
                        if set(extension_directories) != set(managed_by_directory):
                            issues.append(
                                f"{prefix}.extensions_dir directories do not match the frozen product-managed inventory"
                            )
                        for directory, extension in managed_by_directory.items():
                            extension_dir = extension_directories.get(directory)
                            if extension_dir is None:
                                continue
                            package_path = extension_dir / "package.json"
                            if not package_path.is_file():
                                issues.append(
                                    f"{prefix}.extensions_dir/{directory} is missing package.json"
                                )
                                continue
                            if (
                                isinstance(extension.get("package_sha256"), str)
                                and SHA256_PATTERN.fullmatch(extension["package_sha256"])
                                and _file_sha256(package_path)
                                != extension["package_sha256"]
                            ):
                                issues.append(
                                    f"{prefix}.product_managed_extensions package hash does not match {directory}"
                                )
                            try:
                                package = json.loads(package_path.read_text(encoding="utf-8"))
                            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                                issues.append(
                                    f"{prefix}.extensions_dir/{directory}/package.json is invalid: {error}"
                                )
                            else:
                                expected_id = f"{package.get('publisher')}.{package.get('name')}"
                                if expected_id != extension.get("extension_id"):
                                    issues.append(
                                        f"{prefix}.product_managed_extensions extension_id does not match {directory}"
                                    )
                                for field in ("publisher", "version"):
                                    if package.get(field) != extension.get(field):
                                        issues.append(
                                            f"{prefix}.product_managed_extensions {field} does not match {directory}"
                                        )
                        inventory_path = resolved / "extensions.json"
                        if not inventory_path.is_file():
                            issues.append(
                                f"{prefix}.extensions_dir is missing extensions.json"
                            )
                        else:
                            try:
                                inventory = json.loads(
                                    inventory_path.read_text(encoding="utf-8")
                                )
                            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                                issues.append(
                                    f"{prefix}.extensions_dir extensions.json is invalid: {error}"
                                )
                            else:
                                if not isinstance(inventory, list):
                                    issues.append(
                                        f"{prefix}.extensions_dir inventory must be a list"
                                    )
                                else:
                                    inventory_by_id = {
                                        item.get("identifier", {}).get("id"): item
                                        for item in inventory
                                        if isinstance(item, dict)
                                    }
                                    expected_ids = {
                                        item.get("extension_id")
                                        for item in managed_extensions
                                        if isinstance(item, dict)
                                    }
                                    if set(inventory_by_id) != expected_ids:
                                        issues.append(
                                            f"{prefix}.extensions_dir inventory IDs do not match the frozen product-managed inventory"
                                        )
                                    for extension in managed_extensions:
                                        if not isinstance(extension, dict):
                                            continue
                                        item = inventory_by_id.get(
                                            extension.get("extension_id")
                                        )
                                        if item is None:
                                            continue
                                        if item.get("version") != extension.get("version"):
                                            issues.append(
                                                f"{prefix}.extensions_dir inventory version does not match {extension.get('extension_id')}"
                                            )
                                        if (
                                            item.get("metadata", {}).get(
                                                "isApplicationScoped"
                                            )
                                            is not True
                                        ):
                                            issues.append(
                                                f"{prefix}.extensions_dir inventory must mark {extension.get('extension_id')} application-scoped"
                                            )
                            expected_inventory_hash = system.get(
                                "extensions_inventory_sha256"
                            )
                            if (
                                isinstance(expected_inventory_hash, str)
                                and SHA256_PATTERN.fullmatch(expected_inventory_hash)
                                and _file_sha256(inventory_path)
                                != expected_inventory_hash
                            ):
                                issues.append(
                                    f"{prefix}.extensions_inventory_sha256 does not match extensions.json"
                                )
                    elif field == "user_data_dir" and require_frozen:
                        candidates = list(
                            (resolved / "User" / "profiles").glob("*/settings.json")
                        )
                        main_settings = resolved / "User" / "settings.json"
                        if main_settings.is_file():
                            candidates.append(main_settings)
                        candidates = sorted(set(candidates))
                        if len(candidates) != 1:
                            issues.append(
                                f"{prefix}.user_data_dir must contain exactly one active settings.json"
                            )
                        else:
                            expected_settings_hash = system.get(
                                "profile_settings_sha256"
                            )
                            if (
                                isinstance(expected_settings_hash, str)
                                and SHA256_PATTERN.fullmatch(expected_settings_hash)
                                and _file_sha256(candidates[0])
                                != expected_settings_hash
                            ):
                                issues.append(
                                    f"{prefix}.profile_settings_sha256 does not match the active settings file"
                                )

        if require_frozen:
            if not _is_nonempty_text(value["freeze_id"]):
                issues.append("freeze_id must be non-empty when frozen")
            if not _is_nonempty_text(value["observed_at"]):
                issues.append("observed_at must be non-empty when frozen")
            if not (
                _is_nonempty_text(system.get("displayed_default_agent_mode"))
                or _is_nonempty_text(system.get("displayed_default_model"))
            ):
                issues.append(
                    f"{prefix} must record the displayed default agent mode or model"
                )
            if not _is_nonempty_text(system.get("account_tier_label")):
                issues.append(f"{prefix}.account_tier_label must be recorded without PII")
            _validate_hash(
                system.get("profile_settings_sha256"),
                f"{prefix}.profile_settings_sha256",
                issues,
            )
            _validate_hash(
                system.get("extensions_inventory_sha256"),
                f"{prefix}.extensions_inventory_sha256",
                issues,
            )
            _validate_hash(
                system.get("configuration_sha256"),
                f"{prefix}.configuration_sha256",
                issues,
            )
            captures = system.get("captures")
            if not isinstance(captures, dict) or not REQUIRED_CAPTURE_KEYS.issubset(
                captures
            ):
                issues.append(
                    f"{prefix}.captures must contain at least {sorted(REQUIRED_CAPTURE_KEYS)}"
                )
            else:
                for capture_name in sorted(captures):
                    capture = captures[capture_name]
                    if not isinstance(capture, dict):
                        issues.append(f"{prefix}.captures.{capture_name} must be an object")
                        continue
                    if not _is_nonempty_text(capture.get("path")):
                        issues.append(f"{prefix}.captures.{capture_name}.path is required")
                    _validate_hash(
                        capture.get("sha256"),
                        f"{prefix}.captures.{capture_name}.sha256",
                        issues,
                    )
                    capture_path = _resolve_repository_path(
                        capture.get("path"),
                        repository_root=repository_root,
                        label=f"{prefix}.captures.{capture_name}.path",
                        issues=issues,
                    )
                    if verify_files and capture_path is not None:
                        if not capture_path.is_file():
                            issues.append(
                                f"{prefix}.captures.{capture_name}.path must name an existing file"
                            )
                        elif (
                            isinstance(capture.get("sha256"), str)
                            and SHA256_PATTERN.fullmatch(capture["sha256"])
                            and _file_sha256(capture_path) != capture["sha256"]
                        ):
                            issues.append(
                                f"{prefix}.captures.{capture_name}.sha256 does not match the file"
                            )
            restart_observations = system.get("restart_observations")
            if not isinstance(restart_observations, list) or len(
                restart_observations
            ) != 2:
                issues.append(f"{prefix}.restart_observations must contain two records")
            else:
                for index, observation in enumerate(restart_observations, start=1):
                    observation_prefix = f"{prefix}.restart_observations[{index - 1}]"
                    if not isinstance(observation, dict):
                        issues.append(f"{observation_prefix} must be an object")
                        continue
                    if observation.get("sequence") != index:
                        issues.append(f"{observation_prefix}.sequence must equal {index}")
                    if observation.get("evidence_capture") != f"default_agent_reopen{index}":
                        issues.append(
                            f"{observation_prefix}.evidence_capture must reference default_agent_reopen{index}"
                        )
                    observed_model = observation.get("displayed_default_model")
                    if observed_model != system.get("displayed_default_model"):
                        issues.append(
                            f"{observation_prefix}.displayed_default_model must match the frozen default"
                        )
                    anomalies = observation.get("observed_anomalies")
                    if not isinstance(anomalies, list) or not all(
                        _is_nonempty_text(item) for item in anomalies
                    ):
                        issues.append(
                            f"{observation_prefix}.observed_anomalies must be a text list"
                        )
            configuration_hash = system.get("configuration_sha256")
            if (
                isinstance(configuration_hash, str)
                and SHA256_PATTERN.fullmatch(configuration_hash)
                and configuration_hash != system_configuration_sha256(system)
            ):
                issues.append(
                    f"{prefix}.configuration_sha256 does not match the canonical system record"
                )
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the Cursor/Devin dedicated clean-profile freeze manifest."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--allow-unfrozen",
        action="store_true",
        help="Validate structure and clean-profile policy without requiring freeze fields.",
    )
    arguments = parser.parse_args()
    value = json.loads(arguments.manifest.read_text(encoding="utf-8"))
    issues = validate_native_ide_freeze(
        value, require_frozen=not arguments.allow_unfrozen
    )
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        raise SystemExit(1)
    print(f"valid={arguments.manifest.resolve()}")


if __name__ == "__main__":
    main()
