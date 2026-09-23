from __future__ import annotations

import os

from .common import (
    ProbeSession,
    _last_output,
    require_docker,
    resolve_node_environment,
)


def run_local_browser_check(
    session: ProbeSession, *, observation_id: str, expected_mode: str
) -> None:
    node, environment = resolve_node_environment()
    outcome = session.run_command(
        f"browser-{observation_id}",
        [
            node,
            str(session.task_root / "evaluator" / "hidden_tests" / "browser_check.cjs"),
            str(session.workspace),
            expected_mode,
        ],
        environment=environment,
        timeout=60,
    )
    session.record_command(observation_id, outcome)


def run_compose_browser_check(
    session: ProbeSession,
    *,
    project_prefix: str,
    observation_ids: list[str],
    expected_mode: str,
) -> None:
    docker = require_docker(session)
    node, environment = resolve_node_environment()
    project = f"{project_prefix}{os.getpid()}"
    compose = [docker, "compose", "-p", project, "-f", str(session.workspace / "compose.yaml")]
    try:
        up = session.run_command(
            f"{project_prefix}-compose-up",
            compose + ["up", "--build", "--detach", "--wait", "--wait-timeout", "180"],
            timeout=180,
        )
        if up.returncode != 0:
            for observation_id in observation_ids:
                session.record(
                    observation_id,
                    "failed",
                    duration_seconds=up.duration_seconds,
                    detail="Compose stack did not reach the frozen healthy state.",
                    evidence=[up.evidence_path],
                )
            return
        browser = session.run_command(
            f"browser-{project_prefix}",
            [
                node,
                str(session.task_root / "evaluator" / "hidden_tests" / "browser_check.cjs"),
                "http://127.0.0.1:8080",
                expected_mode,
            ],
            environment=environment,
            timeout=90,
        )
        for observation_id in observation_ids:
            session.record(
                observation_id,
                "passed" if browser.returncode == 0 else "failed",
                duration_seconds=browser.duration_seconds,
                detail=None if browser.returncode == 0 else _last_output(browser.output),
                evidence=[browser.evidence_path],
            )
        status = session.run_command(
            f"{project_prefix}-compose-status", compose + ["ps", "--all"], timeout=60
        )
        logs = session.run_command(
            f"{project_prefix}-compose-logs", compose + ["logs", "--no-color"], timeout=120
        )
        session.append_docker_status(project, status.output)
        session.append_docker_logs(project, logs.output)
    finally:
        session.run_command(
            f"{project_prefix}-compose-down",
            compose + ["down", "--volumes", "--remove-orphans", "--rmi", "local"],
            timeout=180,
        )
