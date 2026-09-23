from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from apply_oracle import apply_oracle
from prepare_run import prepare_run


TASK_ROOT = Path(__file__).resolve().parents[1]
BROWSER_CHECK = TASK_ROOT / "evaluator" / "hidden_tests" / "browser_check.cjs"
VALIDATION_TEMP_PARENT = TASK_ROOT.parents[2] / "tmp"
FRONTEND_URL = "http://127.0.0.1:8080"
BACKEND_URL = "http://127.0.0.1:8000"


def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 420,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
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
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stdout}"
        )
    return completed


def wait_for_health(timeout_seconds: float = 45.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{BACKEND_URL}/health", timeout=2) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for backend health: {last_error}")


def users_request() -> tuple[int, object]:
    request = urllib.request.Request(
        f"{BACKEND_URL}/api/users",
        headers={"Origin": FRONTEND_URL},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


def database_scalar(compose: list[str], repository: Path, sql: str) -> str:
    result = run_command(
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
        cwd=repository,
        timeout=60,
    )
    return result.stdout.strip()


def run_browser(mode: str, repository: Path) -> str:
    node_executable = os.environ.get("NODE_EXE") or shutil.which("node")
    if not node_executable:
        raise RuntimeError("Node.js not found; set NODE_EXE")
    result = run_command(
        [node_executable, str(BROWSER_CHECK), FRONTEND_URL, mode],
        cwd=repository,
        timeout=60,
    )
    return result.stdout


def validate_repository(repository: Path, mode: str, project_name: str) -> None:
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker CLI not found")
    compose = [docker, "compose", "-p", project_name, "-f", str(repository / "compose.yaml")]
    try:
        run_command(
            compose + ["up", "--build", "--detach", "--wait", "--wait-timeout", "180"],
            cwd=repository,
            timeout=420,
        )
        health = wait_for_health()
        age_column_count = database_scalar(
            compose,
            repository,
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='users' AND column_name='age';",
        )
        columns = database_scalar(
            compose,
            repository,
            "SELECT string_agg(column_name, ',' ORDER BY ordinal_position) "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='users';",
        )
        row_count = database_scalar(
            compose, repository, "SELECT COUNT(*) FROM users;"
        )
        users_status, users_body = users_request()
        browser_output = run_browser(mode, repository)

        if health != {"status": "ok"}:
            raise RuntimeError(f"Unexpected health response: {health}")
        if age_column_count != "0":
            raise RuntimeError(f"users.age exists; count={age_column_count}")
        if columns != "id,name,email,role":
            raise RuntimeError(f"Unexpected users columns: {columns}")
        if row_count != "3":
            raise RuntimeError(f"Seeded user count changed: {row_count}")

        if mode == "blocked":
            if users_status < 500:
                raise RuntimeError(
                    f"Baseline users endpoint unexpectedly returned {users_status}: {users_body}"
                )
        elif mode == "loaded":
            if users_status != 200 or not isinstance(users_body, list):
                raise RuntimeError(
                    f"Oracle users endpoint returned {users_status}: {users_body}"
                )
            if len(users_body) != 3:
                raise RuntimeError(f"Oracle returned {len(users_body)} users")
            for user in users_body:
                if set(user) != {"id", "name", "email", "role"}:
                    raise RuntimeError(f"Unexpected user contract: {user}")
        else:
            raise ValueError(f"Unknown mode: {mode}")

        print(f"{mode}_health=PASS")
        print(f"{mode}_database_columns={columns}")
        print(f"{mode}_age_column_count={age_column_count}")
        print(f"{mode}_database_row_count={row_count}")
        print(f"{mode}_users_status={users_status}")
        print(browser_output.strip())
    finally:
        run_command(
            compose + ["down", "--volumes", "--remove-orphans"],
            cwd=repository,
            timeout=180,
            check=False,
        )


def main() -> None:
    VALIDATION_TEMP_PARENT.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix="l4-01-compose-", dir=VALIDATION_TEMP_PARENT)
    )
    process_token = str(os.getpid())
    try:
        baseline = prepare_run(temporary_root / "baseline")
        oracle = prepare_run(temporary_root / "oracle")
        apply_oracle(oracle)
        print("[1/2] Validating faulty schema cascade", flush=True)
        validate_repository(baseline, "blocked", f"tsbl401base{process_token}")
        print("[2/2] Validating oracle schema cascade", flush=True)
        validate_repository(oracle, "loaded", f"tsbl401oracle{process_token}")
        print("L4-01 Compose validation: PASS")
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == "__main__":
    main()
