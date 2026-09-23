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
TEMP = TASK_ROOT.parents[2] / "tmp"
BROWSER = TASK_ROOT / "evaluator" / "hidden_tests" / "browser_check.cjs"


def run(command, cwd, check=True, timeout=420):
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


def wait_for_health(url):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if json.loads(response.read()) == {"status": "ok"}:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}")


def post_reset(path):
    request = urllib.request.Request(
        f"http://127.0.0.1:8000{path}",
        data=json.dumps({"email": "maya@example.test"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def validate(repository, mode, project):
    docker = shutil.which("docker")
    compose = [docker, "compose", "-p", project, "-f", str(repository / "compose.yaml")]
    try:
        run(compose + ["up", "--build", "--detach", "--wait", "--wait-timeout", "120"], repository)
        wait_for_health("http://127.0.0.1:8000/health")
        current_status, current = post_reset("/api/v2/auth/password-reset")
        retired_status, _ = post_reset("/api/v1/auth/password-reset")
        assert current_status == 202 and current == {
            "status": "accepted",
            "email": "maya@example.test",
            "request_id": "RST-2048",
        }
        assert retired_status == 404
        node = os.environ.get("NODE_EXE") or shutil.which("node")
        browser = run(
            [node, str(BROWSER), "http://127.0.0.1:8080", mode],
            repository,
            check=False,
            timeout=60,
        )
        if browser.returncode:
            raise RuntimeError(browser.stdout)
        print(f"{mode}_api_routes=PASS")
        print(browser.stdout.strip())
    finally:
        run(compose + ["down", "--volumes", "--remove-orphans"], repository, check=False, timeout=180)


def main():
    TEMP.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="l3-03-compose-", dir=TEMP))
    token = str(os.getpid())
    try:
        baseline = prepare_run(root / "baseline")
        oracle = prepare_run(root / "oracle")
        apply_oracle(oracle)
        validate(baseline, "broken", f"tsbl303base{token}")
        validate(oracle, "working", f"tsbl303oracle{token}")
        print("L3-03 Compose validation: PASS")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()

