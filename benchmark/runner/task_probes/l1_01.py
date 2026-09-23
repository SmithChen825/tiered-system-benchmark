from __future__ import annotations

import os

from .common import (
    ProbeSession,
    record_workspace_isolation,
    require_docker,
    resolve_node_environment,
    run_manifest_pytests,
)


MANUAL_SOURCE_IDS = {
    "local_static_browser_smoke",
    "product_images_render_in_nginx",
}


def run(session: ProbeSession) -> None:
    docker = require_docker(session)
    node, node_environment = resolve_node_environment()
    playwright = session.run_command(
        "l1-playwright-runtime",
        [node, "-e", "require('playwright'); console.log('playwright=ready')"],
        environment=node_environment,
        timeout=30,
    )
    if playwright.returncode != 0:
        from .common import InfrastructureProbeError

        raise InfrastructureProbeError("Playwright is unavailable: " + playwright.output)

    run_manifest_pytests(session)
    record_workspace_isolation(session)

    local_browser = session.run_command(
        "browser-local_static_browser_smoke",
        [
            node,
            str(session.task_root / "evaluator" / "hidden_tests" / "browser_check.cjs"),
            str(session.workspace),
        ],
        environment=node_environment,
        timeout=60,
    )
    session.record_command("local_static_browser_smoke", local_browser)

    token = str(os.getpid())
    image = f"tsb-probe-l1-01:{token}"
    container = f"tsb-probe-l1-01-{token}"
    build = session.run_command(
        "l1-docker-build",
        [docker, "build", "--tag", image, str(session.workspace)],
        timeout=300,
    )
    if build.returncode != 0:
        session.record(
            "product_images_render_in_nginx",
            "failed",
            duration_seconds=build.duration_seconds,
            detail="Final workspace image failed to build.",
            evidence=[build.evidence_path],
        )
        return

    try:
        started = session.run_command(
            "l1-docker-run",
            [
                docker,
                "run",
                "--detach",
                "--name",
                container,
                "--publish",
                "127.0.0.1::80",
                image,
            ],
            timeout=60,
        )
        if started.returncode != 0:
            session.record_command("product_images_render_in_nginx", started)
            return
        port = session.run_command(
            "l1-docker-port",
            [docker, "port", container, "80/tcp"],
            timeout=30,
        )
        if port.returncode != 0 or ":" not in port.output:
            session.record_command("product_images_render_in_nginx", port)
            return
        host_port = port.output.strip().rsplit(":", maxsplit=1)[1]
        browser = session.run_command(
            "browser-product_images_render_in_nginx",
            [
                node,
                str(
                    session.task_root
                    / "evaluator"
                    / "hidden_tests"
                    / "browser_url_check.cjs"
                ),
                f"http://127.0.0.1:{host_port}",
            ],
            environment=node_environment,
            timeout=60,
        )
        session.record_command("product_images_render_in_nginx", browser)
        status = session.run_command(
            "l1-docker-status",
            [docker, "inspect", "--format", "{{json .State}}", container],
            timeout=30,
        )
        logs = session.run_command(
            "l1-docker-logs", [docker, "logs", container], timeout=30
        )
        session.append_docker_status(container, status.output)
        session.append_docker_logs(container, logs.output)
    finally:
        session.run_command(
            "l1-clean-container",
            [docker, "rm", "--force", container],
            timeout=60,
        )
        session.run_command(
            "l1-clean-image",
            [docker, "image", "rm", "--force", image],
            timeout=60,
        )
