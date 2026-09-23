from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from apply_oracle import apply_oracle
from prepare_run import FIXTURE, prepare_run


TASK_ROOT = Path(__file__).resolve().parents[1]
HIDDEN_TESTS = TASK_ROOT / "evaluator" / "hidden_tests" / "test_l2_03.py"
VALIDATION_TEMP_PARENT = TASK_ROOT.parents[2] / "tmp"
EXPECTED_BASELINE_FAILURES = {
    "test_seed_notes_load_from_authoritative_project_store",
    "test_import_and_export_update_the_authoritative_project_store",
    "test_import_survives_restart_from_a_different_working_directory",
    "test_default_storage_path_is_anchored_to_the_project_root",
}


@dataclass(frozen=True)
class TestResult:
    returncode: int
    output: str
    failed_tests: frozenset[str]


def repository_hash(repository: Path) -> str:
    digest = hashlib.sha256()
    ignored_parts = {"__pycache__", ".pytest_cache"}
    files = sorted(
        (path for path in repository.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(repository).as_posix(),
    )
    for path in files:
        if ignored_parts.intersection(path.parts) or path.suffix in {".pyc", ".tmp"}:
            continue
        relative = path.relative_to(repository).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def run_hidden_tests(repository: Path) -> TestResult:
    environment = os.environ.copy()
    environment["L2_03_REPO"] = str(repository)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
            str(HIDDEN_TESTS),
        ],
        cwd=repository / "app",
        env=environment,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    failures = frozenset(
        re.findall(r"FAILED .*::(test_[A-Za-z0-9_]+)", completed.stdout)
    )
    return TestResult(completed.returncode, completed.stdout, failures)


def require_expected_failure(label: str, result: TestResult) -> None:
    if result.returncode == 0:
        raise RuntimeError(f"{label}: faulty fixture unexpectedly passed hidden tests")
    if result.failed_tests != EXPECTED_BASELINE_FAILURES:
        raise RuntimeError(
            f"{label}: expected failures {sorted(EXPECTED_BASELINE_FAILURES)}, "
            f"observed {sorted(result.failed_tests)}\n{result.output}"
        )


def main() -> None:
    fixture_hash = repository_hash(FIXTURE)
    VALIDATION_TEMP_PARENT.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix="l2-03-validation-", dir=VALIDATION_TEMP_PARENT)
    )
    try:
        print("[1/6] Preparing first reset", flush=True)
        first_reset = prepare_run(temporary_root / "baseline-one")
        if repository_hash(first_reset) != fixture_hash:
            raise RuntimeError("First reset does not match the frozen fixture hash")

        print("[2/6] Confirming intended baseline failures", flush=True)
        first_failure = run_hidden_tests(first_reset)
        require_expected_failure("first reset", first_failure)

        print("[3/6] Applying oracle repair", flush=True)
        apply_oracle(first_reset)
        print("[4/6] Confirming oracle passes hidden tests", flush=True)
        repaired = run_hidden_tests(first_reset)
        if repaired.returncode != 0:
            raise RuntimeError(f"Oracle repair failed hidden tests:\n{repaired.output}")

        print("[5/6] Preparing independent second reset", flush=True)
        second_reset = prepare_run(temporary_root / "baseline-two")
        if repository_hash(second_reset) != fixture_hash:
            raise RuntimeError("Second reset does not match the frozen fixture hash")

        print("[6/6] Confirming the same baseline failures", flush=True)
        repeated_failure = run_hidden_tests(second_reset)
        require_expected_failure("second reset", repeated_failure)
        if first_failure.failed_tests != repeated_failure.failed_tests:
            raise RuntimeError("Reset did not reproduce the same hidden-test failures")

        print("L2-03 validation cycle: PASS")
        print(f"fixture_sha256={fixture_hash}")
        print("baseline_failures=" + ",".join(sorted(first_failure.failed_tests)))
        print("oracle_hidden_tests=PASS")
        print("second_reset_same_failure=PASS")
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == "__main__":
    main()

