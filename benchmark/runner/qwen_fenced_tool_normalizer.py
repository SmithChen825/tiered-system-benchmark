from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .common import REPOSITORY_ROOT


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
CONFIG_PATH = (
    REPOSITORY_ROOT
    / "benchmark"
    / "config"
    / "qwen_fenced_tool_normalizer_v3.candidate.json"
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path_hash_issues(
    value: Any, *, repository_root: Path, label: str
) -> list[str]:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        return [f"{label} must contain exactly path and sha256"]
    path_value = value.get("path")
    digest = value.get("sha256")
    if not isinstance(path_value, str) or not path_value or "\\" in path_value:
        return [f"{label}.path must be a repository-relative POSIX path"]
    relative = Path(path_value)
    path = (repository_root / relative).resolve()
    try:
        path.relative_to(repository_root.resolve())
    except ValueError:
        return [f"{label}.path must stay inside the repository"]
    issues: list[str] = []
    if not path.is_file():
        issues.append(f"{label}.path does not exist")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        issues.append(f"{label}.sha256 must be a lowercase SHA-256")
    elif path.is_file() and file_sha256(path) != digest:
        issues.append(f"{label}.sha256 mismatch")
    return issues


def validate_candidate(
    value: dict[str, Any], *, repository_root: Path = REPOSITORY_ROOT
) -> list[str]:
    expected = {
        "schema_version",
        "status",
        "normalizer_id",
        "scope",
        "trigger_evidence",
        "eligibility_requirements",
        "normalization_action",
        "fail_closed",
        "audit",
        "implementation",
        "supporting_changes",
        "live_validation",
    }
    if set(value) != expected:
        return ["normalizer candidate fields do not match the contract"]
    issues: list[str] = []
    if value["schema_version"] != "1.0.0":
        issues.append("schema_version must be 1.0.0")
    if value["normalizer_id"] != "qwen-fenced-tool-json-v3":
        issues.append("normalizer_id mismatch")
    if value["scope"] != "qwen_response_transport_only":
        issues.append("scope mismatch")
    if value["status"] not in {
        "OFFLINE_VALIDATED_LIVE_VALIDATION_PENDING",
        "LIVE_VALIDATED",
    }:
        issues.append("status is not recognized")
    issues.extend(
        _path_hash_issues(
            value["trigger_evidence"],
            repository_root=repository_root,
            label="trigger_evidence",
        )
    )
    issues.extend(
        _path_hash_issues(
            value["implementation"],
            repository_root=repository_root,
            label="implementation",
        )
    )
    changes = value["supporting_changes"]
    if not isinstance(changes, list) or not changes:
        issues.append("supporting_changes must be non-empty")
    else:
        for index, item in enumerate(changes):
            issues.extend(
                _path_hash_issues(
                    item,
                    repository_root=repository_root,
                    label=f"supporting_changes[{index}]",
                )
            )
    action = value["normalization_action"]
    if not isinstance(action, dict) or action.get("semantic_repair_performed") is not False:
        issues.append("normalization_action must prohibit semantic repair")
    audit = value["audit"]
    if not isinstance(audit, dict) or audit.get("records_applied_boolean") is not True:
        issues.append("audit must record the applied decision")
    live = value["live_validation"]
    if not isinstance(live, dict):
        issues.append("live_validation must be an object")
    else:
        status = live.get("status")
        authorized = live.get("authorized")
        if value["status"] == "OFFLINE_VALIDATED_LIVE_VALIDATION_PENDING" and (
            status != "PENDING" or authorized is not False
        ):
            issues.append("offline candidate must retain pending unauthorized live validation")
        if value["status"] == "LIVE_VALIDATED" and (
            status != "PASSED" or authorized is not True
        ):
            issues.append("live-validated candidate must record authorized PASSED")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the Qwen fenced-tool compatibility candidate"
    )
    parser.add_argument("path", nargs="?", type=Path, default=CONFIG_PATH)
    arguments = parser.parse_args()
    value = json.loads(arguments.path.read_text(encoding="utf-8"))
    issues = validate_candidate(value)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        raise SystemExit(1)
    print(f"valid={arguments.path.resolve()}")


if __name__ == "__main__":
    main()
