from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from build_images import BASELINE_IMAGE, ORACLE_IMAGE, build_images


TASK_ROOT = Path(__file__).resolve().parents[1]
HTTP_SCRIPT = r"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

method = sys.argv[1]
path = sys.argv[2]
fields = json.loads(sys.argv[3])
data = urllib.parse.urlencode(fields).encode("utf-8") if method == "POST" else None
request = urllib.request.Request(
    "http://127.0.0.1:8000" + path,
    data=data,
    method=method,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
try:
    with urllib.request.urlopen(request, timeout=5) as response:
        status = response.status
        body = response.read().decode("utf-8")
except urllib.error.HTTPError as error:
    status = error.code
    body = error.read().decode("utf-8")
try:
    parsed = json.loads(body)
except json.JSONDecodeError:
    parsed = body
print(json.dumps({"status": status, "body": parsed}))
"""


def run(
    command: list[str],
    *,
    timeout: int = 180,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=TASK_ROOT,
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


def wait_until_healthy(docker: str, container: str, timeout_seconds: float = 45) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_status = "unknown"
    while time.monotonic() < deadline:
        result = run(
            [
                docker,
                "inspect",
                "--format",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                container,
            ],
            check=False,
        )
        last_status = result.stdout.strip()
        if result.returncode == 0 and last_status == "healthy":
            return
        time.sleep(0.5)
    logs = run([docker, "logs", container], check=False).stdout
    raise RuntimeError(
        f"Container {container} did not become healthy ({last_status}).\n{logs}"
    )


def start_container(docker: str, container: str, volume: str, image: str) -> None:
    run(
        [
            docker,
            "run",
            "--detach",
            "--name",
            container,
            "--env",
            "TASK_DB_PATH=/data/tasks.db",
            "--volume",
            f"{volume}:/data",
            image,
        ]
    )
    wait_until_healthy(docker, container)


def request(
    docker: str,
    container: str,
    method: str,
    path: str,
    fields: dict[str, str] | None = None,
) -> dict[str, object]:
    result = run(
        [
            docker,
            "exec",
            container,
            "python",
            "-c",
            HTTP_SCRIPT,
            method,
            path,
            json.dumps(fields or {}),
        ]
    )
    return json.loads(result.stdout)


def require_status(result: dict[str, object], expected: int, label: str) -> object:
    if result.get("status") != expected:
        raise RuntimeError(f"{label}: expected HTTP {expected}, observed {result}")
    return result.get("body")


def remove_container(docker: str, container: str) -> None:
    run([docker, "rm", "--force", container], check=False)


def remove_volume(docker: str, volume: str) -> None:
    run([docker, "volume", "rm", "--force", volume], check=False)


def validate_baseline(docker: str, token: str) -> None:
    container = f"tsb-l2-02-baseline-{token}"
    volume = f"tsb-l2-02-baseline-{token}"
    try:
        start_container(docker, container, volume, BASELINE_IMAGE)
        require_status(
            request(docker, container, "POST", "/tasks", {"title": "Missing date"}),
            422,
            "baseline omitted due_date",
        )
        require_status(
            request(
                docker,
                container,
                "POST",
                "/tasks",
                {"title": "Empty date", "due_date": ""},
            ),
            422,
            "baseline empty due_date",
        )
        created = require_status(
            request(
                docker,
                container,
                "POST",
                "/tasks",
                {"title": "Dated task", "due_date": "2030-01-15"},
            ),
            201,
            "baseline supplied due_date",
        )
        if not isinstance(created, dict) or created.get("due_date") != "2030-01-15":
            raise RuntimeError(f"Baseline valid task contract changed: {created}")

        remove_container(docker, container)
        start_container(docker, container, volume, BASELINE_IMAGE)
        tasks = require_status(
            request(docker, container, "GET", "/tasks"), 200, "baseline restart"
        )
        if not isinstance(tasks, list) or len(tasks) != 1:
            raise RuntimeError(f"Baseline SQLite data did not survive restart: {tasks}")
        print("baseline_fault=PASS")
        print("baseline_valid_date=PASS")
        print("baseline_persistence=PASS")
    finally:
        remove_container(docker, container)
        remove_volume(docker, volume)


def validate_oracle(docker: str, token: str) -> None:
    container = f"tsb-l2-02-oracle-{token}"
    volume = f"tsb-l2-02-oracle-{token}"
    reset_volume = f"tsb-l2-02-reset-{token}"
    try:
        start_container(docker, container, volume, ORACLE_IMAGE)
        omitted = require_status(
            request(docker, container, "POST", "/tasks", {"title": "Omitted"}),
            201,
            "oracle omitted due_date",
        )
        empty = require_status(
            request(
                docker,
                container,
                "POST",
                "/tasks",
                {"title": "Empty", "due_date": ""},
            ),
            201,
            "oracle empty due_date",
        )
        valid = require_status(
            request(
                docker,
                container,
                "POST",
                "/tasks",
                {"title": "Valid", "due_date": "2030-11-02"},
            ),
            201,
            "oracle supplied due_date",
        )
        require_status(
            request(
                docker,
                container,
                "POST",
                "/tasks",
                {"title": "Malformed", "due_date": "02/11/2030"},
            ),
            422,
            "oracle malformed due_date",
        )
        if not all(isinstance(item, dict) for item in (omitted, empty, valid)):
            raise RuntimeError("Oracle returned an unexpected response contract")
        if omitted.get("due_date") is not None or empty.get("due_date") is not None:
            raise RuntimeError("Oracle did not normalize missing due_date to null")
        if valid.get("due_date") != "2030-11-02":
            raise RuntimeError("Oracle changed supplied due_date")

        remove_container(docker, container)
        start_container(docker, container, volume, ORACLE_IMAGE)
        tasks = require_status(
            request(docker, container, "GET", "/tasks"), 200, "oracle restart"
        )
        if not isinstance(tasks, list) or len(tasks) != 3:
            raise RuntimeError(f"Oracle SQLite data did not survive restart: {tasks}")
        remove_container(docker, container)

        start_container(docker, container, reset_volume, ORACLE_IMAGE)
        reset_tasks = require_status(
            request(docker, container, "GET", "/tasks"), 200, "oracle clean reset"
        )
        if reset_tasks != []:
            raise RuntimeError(f"Fresh volume was not empty: {reset_tasks}")
        print("oracle_optional_due_date=PASS")
        print("oracle_date_validation=PASS")
        print("oracle_null_persistence=PASS")
        print("oracle_restart=PASS")
        print("clean_volume_reset=PASS")
    finally:
        remove_container(docker, container)
        remove_volume(docker, volume)
        remove_volume(docker, reset_volume)


def main() -> None:
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker CLI not found")
    build_images()
    token = str(os.getpid())
    print("[1/2] Validating baseline container", flush=True)
    validate_baseline(docker, token)
    print("[2/2] Validating oracle container", flush=True)
    validate_oracle(docker, token)
    print("L2-02 container validation: PASS")


if __name__ == "__main__":
    main()

