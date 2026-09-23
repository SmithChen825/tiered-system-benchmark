from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .common import TASKS_ROOT, load_json, repository_hash, write_json
except ImportError:  # Supports direct script execution.
    from common import TASKS_ROOT, load_json, repository_hash, write_json  # type: ignore


RUNNER_VERSION = "0.1.0"
OBSERVATION_KEYS = {
    "schema_version",
    "evaluator_version",
    "evaluated_at",
    "observations",
    "docker_status",
    "docker_logs",
    "database_checks",
    "evaluation_error",
}
SOURCE_RESULT_KEYS = {
    "id",
    "status",
    "duration_seconds",
    "detail",
    "evidence",
}
SOURCE_STATUSES = {"passed", "failed", "not_applicable", "unavailable"}


class StructuredEvaluationError(RuntimeError):
    pass


def _require_exact_keys(value: Any, expected: set[str], label: str) -> None:
    if not isinstance(value, dict):
        raise StructuredEvaluationError(f"{label} must be an object")
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    issues: list[str] = []
    if missing:
        issues.append("missing: " + ", ".join(missing))
    if extra:
        issues.append("unknown: " + ", ".join(extra))
    if issues:
        raise StructuredEvaluationError(f"{label} has invalid fields ({'; '.join(issues)})")


def _validate_datetime(value: Any) -> None:
    if not isinstance(value, str):
        raise StructuredEvaluationError("evaluated_at must be an RFC 3339 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise StructuredEvaluationError("evaluated_at is not a valid date-time") from error
    if parsed.tzinfo is None:
        raise StructuredEvaluationError("evaluated_at must include an explicit timezone")


def _validate_error(value: Any) -> None:
    if value is None:
        return
    _require_exact_keys(value, {"classification", "detail"}, "evaluation_error")
    if value["classification"] not in {"evaluator_error", "infrastructure_failure"}:
        raise StructuredEvaluationError("evaluation_error.classification is invalid")
    if not isinstance(value["detail"], str) or not value["detail"]:
        raise StructuredEvaluationError("evaluation_error.detail must be non-empty")


def _source_map(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise StructuredEvaluationError("observations must be an array")
    results: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(value):
        label = f"observations[{index}]"
        _require_exact_keys(item, SOURCE_RESULT_KEYS, label)
        item_id = item["id"]
        if not isinstance(item_id, str) or not re.fullmatch(r"[a-z0-9_]+", item_id):
            raise StructuredEvaluationError(f"{label}.id is invalid")
        if item_id in results:
            raise StructuredEvaluationError(f"duplicate observation ID: {item_id}")
        if item["status"] not in SOURCE_STATUSES:
            raise StructuredEvaluationError(f"{label}.status is invalid")
        duration = item["duration_seconds"]
        if duration is not None and (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or duration < 0
        ):
            raise StructuredEvaluationError(
                f"{label}.duration_seconds must be non-negative or null"
            )
        if item["detail"] is not None and not isinstance(item["detail"], str):
            raise StructuredEvaluationError(f"{label}.detail must be string or null")
        evidence = item["evidence"]
        if not isinstance(evidence, list) or not all(
            isinstance(entry, str) for entry in evidence
        ):
            raise StructuredEvaluationError(f"{label}.evidence must be strings")
        results[item_id] = item
    return results


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _scored_result(
    item_id: str,
    observations: list[tuple[str, str, dict[str, Any]]],
) -> dict[str, Any]:
    available = [
        (source_id, source, item)
        for source_id, source, item in observations
        if item["status"] != "not_applicable"
    ]
    unavailable = [source_id for source_id, _, item in available if item["status"] == "unavailable"]
    if unavailable:
        raise StructuredEvaluationError(
            f"scored check {item_id} has unavailable sources: {', '.join(unavailable)}; "
            "record a failed agent outcome or a formal evaluation_error"
        )
    applicable = bool(available)
    passed = (
        all(item["status"] == "passed" for _, _, item in available)
        if applicable
        else None
    )
    durations = [
        item["duration_seconds"]
        for _, _, item in observations
        if item["duration_seconds"] is not None
    ]
    details = [
        f"{source_id}: {item['detail']}"
        for source_id, _, item in observations
        if item["detail"]
    ]
    evidence: list[str] = []
    for _, source, item in observations:
        _append_unique(evidence, [source, *item["evidence"]])
    return {
        "id": item_id,
        "applicable": applicable,
        "passed": passed,
        "duration_seconds": sum(durations) if durations else None,
        "detail": "\n".join(details) if details else None,
        "evidence": evidence,
    }


def _expected_source_ids(manifest: dict[str, Any]) -> set[str]:
    expected = {item["id"] for item in manifest["functional_tests"]}
    expected.update(item["id"] for item in manifest["operational_evidence"])
    for check in manifest["architecture_checks"]:
        expected.update(item["source_id"] for item in check["evidence"])
    return expected


def build_result_bundle(
    evidence_directory: Path,
    workspace: Path,
    observation_path: Path,
) -> dict[str, Any]:
    evidence_directory = evidence_directory.resolve()
    workspace = workspace.resolve()
    metadata = load_json(evidence_directory / "metadata.json")
    task_id = metadata["task"]["task_id"]
    task_root = TASKS_ROOT / task_id
    manifest = load_json(task_root / "evaluator_manifest.json")
    fixture_manifest = load_json(task_root / "fixture_manifest.json")
    if manifest.get("review_status") != "approved":
        raise StructuredEvaluationError("evaluator manifest is not approved")

    raw = load_json(observation_path.resolve())
    _require_exact_keys(raw, OBSERVATION_KEYS, "observation bundle")
    if raw["schema_version"] != "1.0.0":
        raise StructuredEvaluationError("observation schema_version must be 1.0.0")
    if not isinstance(raw["evaluator_version"], str) or not raw["evaluator_version"]:
        raise StructuredEvaluationError("evaluator_version must be non-empty")
    _validate_datetime(raw["evaluated_at"])
    _validate_error(raw["evaluation_error"])
    if not isinstance(raw["docker_status"], str) or not isinstance(raw["docker_logs"], str):
        raise StructuredEvaluationError("docker_status and docker_logs must be strings")
    if not isinstance(raw["database_checks"], dict):
        raise StructuredEvaluationError("database_checks must be an object")
    sources = _source_map(raw["observations"])

    if raw["evaluation_error"] is not None:
        if sources:
            raise StructuredEvaluationError(
                "formal evaluation errors must not include partial scored observations"
            )
        functional: list[dict[str, Any]] = []
        architecture: list[dict[str, Any]] = []
        operational: list[dict[str, Any]] = []
    else:
        expected = _expected_source_ids(manifest)
        missing = sorted(expected - set(sources))
        extra = sorted(set(sources) - expected)
        if missing or extra:
            detail: list[str] = []
            if missing:
                detail.append("missing: " + ", ".join(missing))
            if extra:
                detail.append("unknown: " + ", ".join(extra))
            raise StructuredEvaluationError(
                "observation coverage does not match the approved manifest ("
                + "; ".join(detail)
                + ")"
            )

        functional = []
        for item in manifest["functional_tests"]:
            functional.append(
                _scored_result(
                    item["id"],
                    [(item["id"], item["source"], sources[item["id"]])],
                )
            )
        architecture = []
        for check in manifest["architecture_checks"]:
            architecture.append(
                _scored_result(
                    check["id"],
                    [
                        (
                            evidence["source_id"],
                            evidence["source"],
                            sources[evidence["source_id"]],
                        )
                        for evidence in check["evidence"]
                    ],
                )
            )
        operational = []
        for item in manifest["operational_evidence"]:
            source = sources[item["id"]]
            evidence: list[str] = []
            _append_unique(evidence, [item["source"], *source["evidence"]])
            operational.append(
                {
                    "id": item["id"],
                    "status": source["status"],
                    "detail": source["detail"],
                    "evidence": evidence,
                }
            )

    return {
        "schema_version": "1.0.0",
        "run_id": metadata["run_id"],
        "task_id": task_id,
        "workspace_sha256": repository_hash(workspace, fixture_manifest),
        "evaluator_version": raw["evaluator_version"],
        "evaluated_at": raw["evaluated_at"],
        "functional_tests": functional,
        "architecture_checks": architecture,
        "operational_evidence": operational,
        "docker_status": raw["docker_status"],
        "docker_logs": raw["docker_logs"],
        "database_checks": raw["database_checks"],
        "evaluation_error": raw["evaluation_error"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a sealed TSB result bundle from task-probe observations."
    )
    parser.add_argument("evidence_directory", type=Path)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("observations", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    bundle = build_result_bundle(
        arguments.evidence_directory,
        arguments.workspace,
        arguments.observations,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(arguments.output, bundle)
    print(f"run_id={bundle['run_id']}")
    print(f"task_id={bundle['task_id']}")
    print(f"workspace_sha256={bundle['workspace_sha256']}")
    print(f"output={arguments.output.resolve()}")


if __name__ == "__main__":
    main()
