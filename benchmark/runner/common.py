from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_ROOT = REPOSITORY_ROOT / "benchmark"
TASKS_ROOT = BENCHMARK_ROOT / "tasks"
SCHEMA_PATH = BENCHMARK_ROOT / "schemas" / "run_metadata.schema.json"

SYSTEM_PROFILES: dict[str, tuple[str, str]] = {
    "cursor": ("cursor", "native_ide"),
    "devin": ("devin", "native_ide"),
    "gpt-5.4": ("gpt-5-4", "api_wrapper"),
    "qwen2.5-coder-7b-instruct": (
        "qwen2-5-coder-7b-instruct",
        "api_wrapper",
    ),
    "baseline": ("baseline", "researcher_validation"),
    "oracle": ("oracle", "researcher_validation"),
}

ARTIFACT_PATHS: dict[str, str] = {
    "task_prompt": "task_prompt.txt",
    "transcript": "transcript.txt",
    "raw_model_response": "raw_model_response.jsonl",
    "adapter_decisions": "adapter_decisions.jsonl",
    "clarification_log": "clarification_log.json",
    "hidden_test_results": "hidden_test_results.json",
    "architecture_checks": "architecture_checks.json",
    "docker_status": "docker_status.txt",
    "docker_logs": "docker_logs.txt",
    "database_checks": "database_checks.json",
    "final_diff": "final.diff",
}

BANNED_WORKSPACE_NAMES = {
    "evaluator",
    "oracle",
    "task_spec.json",
    "fixture_manifest.json",
    "clarification_policy.json",
    "validation_report.md",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def hash_exclusions(manifest: dict[str, Any]) -> tuple[set[str], set[str]]:
    ignored_directories: set[str] = set()
    ignored_suffixes: set[str] = set()
    for item in manifest.get("excluded_from_hash", []):
        if not isinstance(item, str):
            continue
        if item.endswith(" directories"):
            ignored_directories.add(item[: -len(" directories")])
        elif item.endswith(" files"):
            ignored_suffixes.add(item[: -len(" files")])
    return ignored_directories, ignored_suffixes


def repository_hash(repository: Path, manifest: dict[str, Any]) -> str:
    ignored_directories, ignored_suffixes = hash_exclusions(manifest)
    # The deterministic start-state repository is added after fixture hashing.
    # Git metadata is never part of the frozen content hash.
    ignored_directories.add(".git")
    digest = hashlib.sha256()
    files = sorted(
        (path for path in repository.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(repository).as_posix(),
    )
    for path in files:
        relative = path.relative_to(repository)
        if ignored_directories.intersection(relative.parts):
            continue
        if path.suffix in ignored_suffixes:
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_run_id(
    phase: str,
    task_id: str,
    system_slug: str,
    repetition: int,
    attempt: int,
) -> str:
    return (
        f"{phase}-{task_id}-{system_slug}-"
        f"r{repetition:02d}-a{attempt:02d}"
    )
