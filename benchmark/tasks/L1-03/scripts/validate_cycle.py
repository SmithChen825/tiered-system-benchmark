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
HIDDEN_TESTS = TASK_ROOT / "evaluator" / "hidden_tests" / "test_l1_03.py"
BROWSER_CHECK = TASK_ROOT / "evaluator" / "hidden_tests" / "browser_check.cjs"
VALIDATION_TEMP_PARENT = TASK_ROOT.parents[2] / "tmp"
EXPECTED_PYTEST_FAILURES = {"test_contact_form_loads_existing_validation_script"}


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    output: str
    failed_tests: frozenset[str] = frozenset()


def repository_hash(repository: Path) -> str:
    digest = hashlib.sha256()
    ignored_parts = {"__pycache__", ".pytest_cache"}
    files = sorted(
        (path for path in repository.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(repository).as_posix(),
    )
    for path in files:
        if ignored_parts.intersection(path.parts) or path.suffix == ".pyc":
            continue
        relative = path.relative_to(repository).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def run_pytest(repository: Path) -> ProcessResult:
    environment = os.environ.copy()
    environment["L1_03_REPO"] = str(repository)
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
    failed_tests = frozenset(
        re.findall(r"FAILED .*::(test_[A-Za-z0-9_]+)", completed.stdout)
    )
    return ProcessResult(completed.returncode, completed.stdout, failed_tests)


def run_browser_check(repository: Path, expected: str) -> ProcessResult:
    node_executable = os.environ.get("NODE_EXE") or shutil.which("node")
    if not node_executable:
        raise RuntimeError("Node.js not found; set NODE_EXE for the browser evaluator")
    completed = subprocess.run(
        [node_executable, str(BROWSER_CHECK), str(repository), expected],
        cwd=repository,
        env=os.environ.copy(),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return ProcessResult(completed.returncode, completed.stdout)


def require_baseline(
    label: str, pytest_result: ProcessResult, browser_result: ProcessResult
) -> None:
    if pytest_result.returncode == 0:
        raise RuntimeError(f"{label}: faulty fixture unexpectedly passed pytest")
    if pytest_result.failed_tests != EXPECTED_PYTEST_FAILURES:
        raise RuntimeError(
            f"{label}: expected pytest failures {sorted(EXPECTED_PYTEST_FAILURES)}, "
            f"observed {sorted(pytest_result.failed_tests)}\n{pytest_result.output}"
        )
    if browser_result.returncode != 0 or '"/assets/contact-validation.js":404' not in browser_result.output:
        raise RuntimeError(
            f"{label}: browser did not reproduce the missing validation bundle\n"
            f"{browser_result.output}"
        )


def main() -> None:
    fixture_hash = repository_hash(FIXTURE)
    VALIDATION_TEMP_PARENT.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix="l1-03-validation-", dir=VALIDATION_TEMP_PARENT)
    )
    try:
        print("[1/7] Preparing first reset", flush=True)
        first_reset = prepare_run(temporary_root / "baseline-one")
        if repository_hash(first_reset) != fixture_hash:
            raise RuntimeError("First reset does not match the fixture hash")

        print("[2/7] Confirming intended source failure", flush=True)
        first_pytest = run_pytest(first_reset)
        print("[3/7] Confirming intended Chromium failure", flush=True)
        first_browser = run_browser_check(first_reset, "broken")
        require_baseline("first reset", first_pytest, first_browser)

        print("[4/7] Applying oracle and checking all evaluators", flush=True)
        apply_oracle(first_reset)
        repaired_pytest = run_pytest(first_reset)
        repaired_browser = run_browser_check(first_reset, "working")
        if repaired_pytest.returncode != 0:
            raise RuntimeError(f"Oracle failed pytest:\n{repaired_pytest.output}")
        if repaired_browser.returncode != 0:
            raise RuntimeError(f"Oracle failed browser check:\n{repaired_browser.output}")

        print("[5/7] Preparing independent second reset", flush=True)
        second_reset = prepare_run(temporary_root / "baseline-two")
        if repository_hash(second_reset) != fixture_hash:
            raise RuntimeError("Second reset does not match the fixture hash")

        print("[6/7] Repeating source and Chromium checks", flush=True)
        second_pytest = run_pytest(second_reset)
        second_browser = run_browser_check(second_reset, "broken")
        require_baseline("second reset", second_pytest, second_browser)
        if first_pytest.failed_tests != second_pytest.failed_tests:
            raise RuntimeError("Second reset did not reproduce the pytest failures")

        print("[7/7] Validation complete", flush=True)
        print("L1-03 validation cycle: PASS")
        print(f"fixture_sha256={fixture_hash}")
        print("baseline_pytest_failures=" + ",".join(sorted(first_pytest.failed_tests)))
        print("baseline_browser_contact_form=broken")
        print("oracle_pytest=PASS")
        print("oracle_browser=PASS")
        print("second_reset_same_failure=PASS")
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == "__main__":
    main()

