from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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
EXPECTED_ORIGIN = FRONTEND_URL


def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 300,
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


def wait_for_json(url: str, timeout_seconds: float = 30.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def cors_get() -> tuple[int, str | None, dict[str, object]]:
    request = urllib.request.Request(
        f"{BACKEND_URL}/api/account",
        headers={"Origin": EXPECTED_ORIGIN},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        body = json.loads(response.read().decode("utf-8"))
        return response.status, response.headers.get("Access-Control-Allow-Origin"), body


def cors_preflight() -> tuple[int, str | None]:
    request = urllib.request.Request(
        f"{BACKEND_URL}/api/account",
        method="OPTIONS",
        headers={
            "Origin": EXPECTED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.headers.get("Access-Control-Allow-Origin")
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Access-Control-Allow-Origin")


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
            compose + ["up", "--build", "--detach", "--wait", "--wait-timeout", "120"],
            cwd=repository,
            timeout=300,
        )
        health = wait_for_json(f"{BACKEND_URL}/health")
        account = wait_for_json(f"{BACKEND_URL}/api/account")
        get_status, get_origin, cors_account = cors_get()
        preflight_status, preflight_origin = cors_preflight()
        browser_output = run_browser(mode, repository)

        if health != {"status": "ok"}:
            raise RuntimeError(f"Unexpected health response: {health}")
        if account.get("name") != "Ada Lovelace" or cors_account != account:
            raise RuntimeError(f"Unexpected account contract: {account}")
        if get_status != 200:
            raise RuntimeError(f"CORS GET returned HTTP {get_status}")

        if mode == "blocked":
            if get_origin is not None or preflight_status == 200 or preflight_origin is not None:
                raise RuntimeError(
                    "Baseline unexpectedly authorised the frozen frontend origin"
                )
        elif mode == "loaded":
            if get_origin != EXPECTED_ORIGIN:
                raise RuntimeError(f"Oracle GET CORS header is {get_origin!r}")
            if preflight_status != 200 or preflight_origin != EXPECTED_ORIGIN:
                raise RuntimeError(
                    f"Oracle preflight was {preflight_status}, {preflight_origin!r}"
                )
        else:
            raise ValueError(f"Unknown validation mode: {mode}")

        print(f"{mode}_health=PASS")
        print(f"{mode}_direct_account=PASS")
        print(f"{mode}_cors_get_origin={get_origin}")
        print(f"{mode}_preflight_status={preflight_status}")
        print(browser_output.strip())
    finally:
        run_command(
            compose + ["down", "--volumes", "--remove-orphans"],
            cwd=repository,
            timeout=120,
            check=False,
        )


def main() -> None:
    VALIDATION_TEMP_PARENT.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix="l3-01-compose-", dir=VALIDATION_TEMP_PARENT)
    )
    process_token = str(os.getpid())
    try:
        baseline = prepare_run(temporary_root / "baseline")
        oracle = prepare_run(temporary_root / "oracle")
        apply_oracle(oracle)

        print("[1/2] Validating faulty Compose state", flush=True)
        validate_repository(baseline, "blocked", f"tsbl301base{process_token}")
        print("[2/2] Validating oracle Compose state", flush=True)
        validate_repository(oracle, "loaded", f"tsbl301oracle{process_token}")
        print("L3-01 Compose validation: PASS")
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == "__main__":
    main()
