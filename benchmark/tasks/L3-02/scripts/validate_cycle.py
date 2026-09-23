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
HIDDEN_TESTS = TASK_ROOT / "evaluator" / "hidden_tests" / "test_l3_02.py"
VALIDATION_TEMP_PARENT = TASK_ROOT.parents[2] / "tmp"
EXPECTED_FAILURES = {"test_frontend_consumes_the_current_order_status_field"}


@dataclass(frozen=True)
class TestResult:
    returncode: int
    output: str
    failed_tests: frozenset[str]


def repository_hash(repository: Path) -> str:
    digest = hashlib.sha256()
    ignored_parts = {"__pycache__", ".pytest_cache", "node_modules", "dist"}
    files = sorted(
        (path for path in repository.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(repository).as_posix(),
    )
    for path in files:
        if ignored_parts.intersection(path.parts):
            continue
        if path.suffix == ".pyc":
            continue
        relative = path.relative_to(repository).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def run_hidden_tests(repository: Path) -> TestResult:
    environment = os.environ.copy()
    environment["L3_02_REPO"] = str(repository)
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
        cwd=repository,
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
    if result.failed_tests != EXPECTED_FAILURES:
        raise RuntimeError(
            f"{label}: expected {sorted(EXPECTED_FAILURES)}, "
            f"observed {sorted(result.failed_tests)}\n{result.output}"
        )


def main() -> None:
    fixture_hash = repository_hash(FIXTURE)
    VALIDATION_TEMP_PARENT.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix="l3-02-validation-", dir=VALIDATION_TEMP_PARENT)
    )
    try:
        print("[1/6] Preparing first reset", flush=True)
        first_reset = prepare_run(temporary_root / "baseline-one")
        if repository_hash(first_reset) != fixture_hash:
            raise RuntimeError("First reset does not match the fixture hash")

        print("[2/6] Confirming intended contract failure", flush=True)
        first_failure = run_hidden_tests(first_reset)
        require_expected_failure("first reset", first_failure)

        print("[3/6] Applying oracle and checking hidden tests", flush=True)
        apply_oracle(first_reset)
        repaired = run_hidden_tests(first_reset)
        if repaired.returncode != 0:
            raise RuntimeError(f"Oracle failed hidden tests:\n{repaired.output}")

        print("[4/6] Preparing independent second reset", flush=True)
        second_reset = prepare_run(temporary_root / "baseline-two")
        if repository_hash(second_reset) != fixture_hash:
            raise RuntimeError("Second reset does not match the fixture hash")

        print("[5/6] Confirming the same contract failure", flush=True)
        repeated = run_hidden_tests(second_reset)
        require_expected_failure("second reset", repeated)
        if repeated.failed_tests != first_failure.failed_tests:
            raise RuntimeError("Second reset did not reproduce the same failures")

        print("[6/6] Validation complete", flush=True)
        print("L3-02 validation cycle: PASS")
        print(f"fixture_sha256={fixture_hash}")
        print("baseline_failures=" + ",".join(sorted(first_failure.failed_tests)))
        print("oracle_hidden_tests=PASS")
        print("second_reset_same_failure=PASS")
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == "__main__":
    main()
