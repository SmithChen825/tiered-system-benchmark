from __future__ import annotations

import os

from .common import (
    InfrastructureProbeError,
    ProbeSession,
    record_workspace_isolation,
    require_docker,
    resolve_node_environment,
    run_manifest_pytests,
)


MANUAL_SOURCE_IDS = {
    "browser_account_loads",
    "compose_service_health",
}


def run(session: ProbeSession) -> None:
    docker = require_docker(session)
    node, node_environment = resolve_node_environment()
    playwright = session.run_command(
        "l3-playwright-runtime",
        [node, "-e", "require('playwright'); console.log('playwright=ready')"],
        environment=node_environment,
        timeout=30,
    )
    if playwright.returncode != 0:
        raise InfrastructureProbeError("Playwright is unavailable: " + playwright.output)

    run_manifest_pytests(session)
    record_workspace_isolation(session)

    project = f"tsbl301probe{os.getpid()}"
    compose = [
        docker,
        "compose",
        "-p",
        project,
        "-f",
        str(session.workspace / "compose.yaml"),
    ]
    up = session.run_command(
        "l3-compose-up",
        compose + ["up", "--build", "--detach", "--wait", "--wait-timeout", "120"],
        timeout=360,
    )
    session.record(
        "compose_service_health",
        "passed" if up.returncode == 0 else "failed",
        duration_seconds=up.duration_seconds,
        detail=None if up.returncode == 0 else "Compose services did not become healthy.",
        evidence=[up.evidence_path],
    )
    try:
        if up.returncode == 0:
            browser = session.run_command(
                "l3-browser-account-loads",
                [
                    node,
                    str(
                        session.task_root
                        / "evaluator"
                        / "hidden_tests"
                        / "browser_check.cjs"
                    ),
                    "http://127.0.0.1:8080",
                    "loaded",
                ],
                environment=node_environment,
                timeout=60,
            )
            session.record_command("browser_account_loads", browser)
        else:
            session.record(
                "browser_account_loads",
                "failed",
                detail="Browser contract could not load because Compose startup failed.",
                evidence=[up.evidence_path],
            )
        status = session.run_command(
            "l3-compose-status", compose + ["ps", "--all"], timeout=60
        )
        logs = session.run_command(
            "l3-compose-logs", compose + ["logs", "--no-color"], timeout=120
        )
        session.append_docker_status(project, status.output)
        session.append_docker_logs(project, logs.output)
    finally:
        session.run_command(
            "l3-compose-down",
            compose + ["down", "--volumes", "--remove-orphans", "--rmi", "local"],
            timeout=180,
        )
