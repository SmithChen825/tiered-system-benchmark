from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .common import REPOSITORY_ROOT


CONFIG_PATH = REPOSITORY_ROOT / "benchmark" / "config" / "qwen_deployment.json"
SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _path_hash(value: Any, *, label: str, repository_root: Path) -> list[str]:
    if not isinstance(value, dict) or not {"path", "sha256"}.issubset(value):
        return [f"{label} must contain path and sha256"]
    raw = value.get("path")
    digest = value.get("sha256")
    if not isinstance(raw, str) or not raw or "\\" in raw or ".." in Path(raw).parts:
        return [f"{label}.path must be repository-relative POSIX"]
    path = (repository_root / raw).resolve()
    try:
        path.relative_to(repository_root.resolve())
    except ValueError:
        return [f"{label}.path escapes repository"]
    issues: list[str] = []
    if not path.is_file():
        issues.append(f"{label}.path does not exist")
    if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
        issues.append(f"{label}.sha256 is invalid")
    elif path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        issues.append(f"{label}.sha256 mismatch")
    return issues


def validate_qwen_deployment_freeze(
    value: dict[str, Any], *, repository_root: Path = REPOSITORY_ROOT
) -> list[str]:
    expected = {
        "schema_version", "status", "freeze_scope", "deployment_id", "frozen_at",
        "endpoint", "effective_configuration", "amendment_lineage",
        "live_verification", "execution_boundary",
    }
    if set(value) != expected:
        return ["Qwen deployment freeze fields do not match the contract"]
    issues: list[str] = []
    if value["schema_version"] != "1.0.0" or value["status"] != "FROZEN":
        issues.append("Qwen deployment must be schema 1.0.0 and FROZEN")
    if value["freeze_scope"] != "pilot_candidate":
        issues.append("Qwen deployment freeze_scope must be pilot_candidate")
    endpoint = value["endpoint"]
    if not isinstance(endpoint, dict) or endpoint.get("name") != "tsb-api-pilot-2026-r4":
        issues.append("Qwen frozen endpoint identity mismatch")
    elif endpoint.get("final_idle_state") != "scaledToZero":
        issues.append("Qwen frozen endpoint must end scaledToZero")
    effective = value["effective_configuration"]
    if not isinstance(effective, dict):
        issues.append("effective_configuration must be an object")
    else:
        for label in ("base_candidate", "chat_template", "compatibility_normalizer"):
            issues.extend(_path_hash(effective.get(label), label=label, repository_root=repository_root))
        if effective.get("container_argument_count") != 23:
            issues.append("effective container argument count must be 23")
        if effective.get("tool_call_parser") != "hermes" or effective.get("tool_choice") != "auto":
            issues.append("frozen Hermes/auto tool settings mismatch")
        normalizer = effective.get("compatibility_normalizer") or {}
        if normalizer.get("status") != "LIVE_VALIDATED":
            issues.append("compatibility normalizer must be LIVE_VALIDATED")
    lineage = value["amendment_lineage"]
    if not isinstance(lineage, list) or len(lineage) != 4:
        issues.append("amendment_lineage must bind exactly four reviewed amendments")
    else:
        for index, item in enumerate(lineage):
            issues.extend(_path_hash(item.get("record"), label=f"amendment_lineage[{index}].record", repository_root=repository_root))
            issues.extend(_path_hash(item.get("provider_update"), label=f"amendment_lineage[{index}].provider_update", repository_root=repository_root))
    live = value["live_verification"]
    if not isinstance(live, dict) or live.get("status") != "PASSED":
        issues.append("live_verification must be PASSED")
    else:
        gates = live.get("gates")
        if not isinstance(gates, dict) or any(not str(status).startswith("PASSED") for status in gates.values()):
            issues.append("all Qwen live verification gates must pass")
        evidence = live.get("evidence")
        if not isinstance(evidence, dict):
            issues.append("live_verification.evidence must be an object")
        else:
            for name, item in evidence.items():
                issues.extend(_path_hash(item, label=f"live_verification.evidence.{name}", repository_root=repository_root))
    boundary = value["execution_boundary"]
    if not isinstance(boundary, dict) or boundary.get("this_record_alone_authorizes_pilot_execution") is not False:
        issues.append("deployment freeze must not independently authorize pilot execution")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the frozen Qwen deployment record")
    parser.add_argument("path", nargs="?", type=Path, default=CONFIG_PATH)
    args = parser.parse_args()
    value = json.loads(args.path.read_text(encoding="utf-8"))
    issues = validate_qwen_deployment_freeze(value)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        raise SystemExit(1)
    print(f"valid={args.path.resolve()}")


if __name__ == "__main__":
    main()
