from __future__ import annotations

import json
import os
import time

from .common import (
    ProbeSession,
    record_workspace_isolation,
    require_docker,
    run_manifest_pytests,
)


MANUAL_SOURCE_IDS = {
    "container_restart_persistence",
    "clean_sqlite_volume_reset",
}


HTTP_SCRIPT = r"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

method, path, fields_json = sys.argv[1:4]
fields = json.loads(fields_json)
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
    body = json.loads(body)
except json.JSONDecodeError:
    pass
print(json.dumps({"status": status, "body": body}))
"""


def _start(
    session: ProbeSession,
    docker: str,
    container: str,
    volume: str,
    image: str,
    label: str,
) -> tuple[bool, list[str]]:
    evidence: list[str] = []
    started = session.run_command(
        f"{label}-run",
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
        ],
        timeout=60,
    )
    evidence.append(started.evidence_path)
    if started.returncode != 0:
        return False, evidence
    deadline = time.monotonic() + 45
    index = 0
    while time.monotonic() < deadline:
        health = session.run_command(
            f"{label}-health-{index}",
            [
                docker,
                "inspect",
                "--format",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                container,
            ],
            timeout=15,
        )
        evidence.append(health.evidence_path)
        if health.returncode == 0 and health.output.strip() == "healthy":
            return True, evidence
        index += 1
        time.sleep(0.5)
    return False, evidence


def _request(
    session: ProbeSession,
    docker: str,
    container: str,
    label: str,
    method: str,
    path: str,
    fields: dict[str, str] | None = None,
) -> tuple[dict | None, str]:
    outcome = session.run_command(
        label,
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
        ],
        timeout=30,
    )
    if outcome.returncode != 0:
        return None, outcome.evidence_path
    try:
        return json.loads(outcome.output), outcome.evidence_path
    except json.JSONDecodeError:
        return None, outcome.evidence_path


def run(session: ProbeSession) -> None:
    docker = require_docker(session)
    run_manifest_pytests(session)
    record_workspace_isolation(session)

    token = str(os.getpid())
    image = f"tsb-probe-l2-02:{token}"
    container = f"tsb-probe-l2-02-{token}"
    volume = f"tsb-probe-l2-02-data-{token}"
    reset_volume = f"tsb-probe-l2-02-reset-{token}"
    evidence: list[str] = []
    persistence_passed = False
    reset_passed = False
    details: dict[str, object] = {}
    build = session.run_command(
        "l2-docker-build",
        [docker, "build", "--tag", image, str(session.workspace)],
        timeout=420,
    )
    evidence.append(build.evidence_path)
    try:
        if build.returncode == 0:
            healthy, start_evidence = _start(
                session, docker, container, volume, image, "l2-primary"
            )
            evidence.extend(start_evidence)
            if healthy:
                created, path = _request(
                    session,
                    docker,
                    container,
                    "l2-create-persistent-task",
                    "POST",
                    "/tasks",
                    {"title": "Persistence probe", "due_date": "2030-01-15"},
                )
                evidence.append(path)
                session.run_command(
                    "l2-stop-primary",
                    [docker, "rm", "--force", container],
                    timeout=60,
                )
                healthy, restart_evidence = _start(
                    session, docker, container, volume, image, "l2-restart"
                )
                evidence.extend(restart_evidence)
                retrieved = None
                if healthy:
                    retrieved, path = _request(
                        session,
                        docker,
                        container,
                        "l2-retrieve-after-restart",
                        "GET",
                        "/tasks",
                    )
                    evidence.append(path)
                body = retrieved.get("body") if isinstance(retrieved, dict) else None
                persistence_passed = bool(
                    isinstance(created, dict)
                    and created.get("status") == 201
                    and isinstance(body, list)
                    and any(
                        isinstance(item, dict)
                        and item.get("title") == "Persistence probe"
                        for item in body
                    )
                )
                details["created"] = created
                details["retrieved_after_restart"] = retrieved
                session.run_command(
                    "l2-stop-restarted",
                    [docker, "rm", "--force", container],
                    timeout=60,
                )

            clean_healthy, clean_evidence = _start(
                session, docker, container, reset_volume, image, "l2-clean-volume"
            )
            evidence.extend(clean_evidence)
            if clean_healthy:
                clean, path = _request(
                    session,
                    docker,
                    container,
                    "l2-clean-volume-list",
                    "GET",
                    "/tasks",
                )
                evidence.append(path)
                reset_passed = bool(
                    isinstance(clean, dict)
                    and clean.get("status") == 200
                    and clean.get("body") == []
                )
                details["fresh_volume"] = clean

            status = session.run_command(
                "l2-docker-status",
                [docker, "ps", "--all", "--filter", f"name={container}"],
                timeout=30,
            )
            logs = session.run_command(
                "l2-docker-logs", [docker, "logs", container], timeout=30
            )
            session.append_docker_status(container, status.output)
            session.append_docker_logs(container, logs.output)
    finally:
        session.run_command(
            "l2-clean-container",
            [docker, "rm", "--force", container],
            timeout=60,
        )
        for label, name in (("data", volume), ("reset", reset_volume)):
            session.run_command(
                f"l2-clean-{label}-volume",
                [docker, "volume", "rm", "--force", name],
                timeout=60,
            )
        session.run_command(
            "l2-clean-image",
            [docker, "image", "rm", "--force", image],
            timeout=60,
        )

    failure_detail = None if build.returncode == 0 else "Final workspace image failed to build."
    session.record(
        "container_restart_persistence",
        "passed" if persistence_passed else "failed",
        detail=failure_detail or (None if persistence_passed else "Create/restart/retrieve probe failed."),
        evidence=evidence,
    )
    session.record(
        "clean_sqlite_volume_reset",
        "passed" if reset_passed else "failed",
        detail=failure_detail or (None if reset_passed else "Fresh-volume reset probe failed."),
        evidence=evidence,
    )
    session.database_checks = {
        "status": "completed",
        "checks": [
            {"id": "container_restart_persistence", "passed": persistence_passed},
            {"id": "clean_sqlite_volume_reset", "passed": reset_passed},
        ],
        "details": details,
    }
