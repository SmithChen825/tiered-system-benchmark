from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from apply_oracle import apply_oracle
from prepare_run import prepare_run


TASK_ROOT = Path(__file__).resolve().parents[1]
TEMP = TASK_ROOT.parents[2] / "tmp"
BROWSER = TASK_ROOT / "evaluator" / "hidden_tests" / "browser_check.cjs"
API = "http://127.0.0.1:8000"


def run(command, cwd, check=True, timeout=600):
    result = subprocess.run(
        command,
        cwd=cwd,
        env=os.environ.copy(),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(f"Command failed: {' '.join(command)}\n{result.stdout}")
    return result


def wait_url(url, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return response.status, response.read()
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}")


def scalar(compose, repository, sql):
    result = run(
        compose
        + [
            "exec",
            "--no-TTY",
            "db",
            "psql",
            "--username",
            "benchmark",
            "--dbname",
            "benchmark",
            "--tuples-only",
            "--no-align",
            "--command",
            sql,
        ],
        repository,
        timeout=60,
    )
    return result.stdout.strip()


def browser_check(repository, expected):
    node = os.environ.get("NODE_EXE") or shutil.which("node")
    result = run(
        [node, str(BROWSER), "http://127.0.0.1:8080", expected],
        repository,
        check=False,
        timeout=90,
    )
    if result.returncode:
        raise RuntimeError(result.stdout)
    return result.stdout.strip()


def validate_baseline(repository, project):
    docker = shutil.which("docker")
    compose = [docker, "compose", "-p", project, "-f", str(repository / "compose.yaml")]
    try:
        run(compose + ["up", "--build", "--detach"], repository, check=False)
        wait_url("http://127.0.0.1:8080")
        assert scalar(compose, repository, "SELECT COUNT(*) FROM dashboard_metrics;") == "3"
        backend_id = run(compose + ["ps", "--all", "--quiet", "backend"], repository).stdout.strip()
        if not backend_id:
            raise RuntimeError("Baseline backend container was not created")
        deadline = time.monotonic() + 45
        state = ""
        while time.monotonic() < deadline:
            state = run(
                [docker, "inspect", "--format", "{{.State.Status}}", backend_id],
                repository,
                check=False,
                timeout=15,
            ).stdout.strip()
            if state in {"exited", "dead"}:
                break
            time.sleep(0.25)
        if state not in {"exited", "dead"}:
            raise RuntimeError(f"Baseline backend unexpectedly remained {state}")
        logs = run(compose + ["logs", "--no-color", "backend"], repository, check=False).stdout
        if "OperationalError" not in logs and "could not translate host name" not in logs:
            raise RuntimeError(f"Baseline logs did not show database connection failure:\n{logs}")
        browser = browser_check(repository, "broken")
        print(f"baseline_backend_state={state}")
        print("baseline_database_rows=3")
        print(browser)
    finally:
        run(compose + ["down", "--volumes", "--remove-orphans"], repository, check=False, timeout=180)


def validate_oracle(repository, project):
    docker = shutil.which("docker")
    compose = [docker, "compose", "-p", project, "-f", str(repository / "compose.yaml")]
    try:
        run(
            compose + ["up", "--build", "--detach", "--wait", "--wait-timeout", "180"],
            repository,
        )
        status, health_raw = wait_url(f"{API}/health")
        health = json.loads(health_raw)
        assert status == 200 and health == {"status": "ok", "database": "reachable"}
        status, dashboard_raw = wait_url(f"{API}/api/dashboard")
        dashboard = json.loads(dashboard_raw)
        assert status == 200
        assert dashboard == {
            "status": "operational",
            "database": "reachable",
            "metrics": [
                {"name": "Jobs processed", "value": 128},
                {"name": "Active workers", "value": 4},
                {"name": "Pending alerts", "value": 0},
            ],
        }
        assert scalar(compose, repository, "SELECT COUNT(*) FROM dashboard_metrics;") == "3"
        browser = browser_check(repository, "loaded")
        print("oracle_compose_health=PASS")
        print("oracle_dashboard_api=PASS")
        print(browser)
    finally:
        run(compose + ["down", "--volumes", "--remove-orphans"], repository, check=False, timeout=180)


def main():
    TEMP.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="l4-03-compose-", dir=TEMP))
    token = str(os.getpid())
    try:
        baseline = prepare_run(root / "baseline")
        oracle = prepare_run(root / "oracle")
        apply_oracle(oracle)
        validate_baseline(baseline, f"tsbl403base{token}")
        validate_oracle(oracle, f"tsbl403oracle{token}")
        print("L4-03 Compose validation: PASS")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()

