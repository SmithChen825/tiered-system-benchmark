from __future__ import annotations

import json
import sys

from .common import (
    ProbeSession,
    record_workspace_isolation,
    require_docker,
    resolve_node_environment,
    run_manifest_pytests,
)


HTTP_CHECK = r'''import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:8000/api/dashboard", timeout=10) as response:
    value = json.loads(response.read())
assert response.status == 200
assert value == {"status":"operational","database":"reachable","metrics":[{"name":"Jobs processed","value":128},{"name":"Active workers","value":4},{"name":"Pending alerts","value":0}]}
print(json.dumps(value, sort_keys=True))'''


def run(session: ProbeSession) -> None:
    run_manifest_pytests(session)
    docker = require_docker(session)
    node, environment = resolve_node_environment()
    project = f"tsbprobe-l403-{__import__('os').getpid()}"
    compose = [docker, "compose", "-p", project, "-f", str(session.workspace / "compose.yaml")]
    try:
        up = session.run_command(
            "l4-03-compose-up",
            compose + ["up", "--build", "--detach", "--wait", "--wait-timeout", "180"],
            timeout=180,
        )
        session.record_command("compose_health", up)
        if up.returncode == 0:
            api = session.run_command(
                "l4-03-dashboard-api", [sys.executable, "-c", HTTP_CHECK], timeout=30
            )
            session.record_command("dashboard_api", api)
            browser = session.run_command(
                "browser-l4-03",
                [node, str(session.task_root / "evaluator" / "hidden_tests" / "browser_check.cjs"), "http://127.0.0.1:8080", "loaded"],
                environment=environment,
                timeout=90,
            )
            session.record_command("browser_dashboard", browser)
        else:
            for observation_id in ("dashboard_api", "browser_dashboard"):
                session.record(
                    observation_id,
                    "failed",
                    detail="Compose stack did not reach the frozen healthy state.",
                    evidence=[up.evidence_path],
                )
        status = session.run_command("l4-03-compose-status", compose + ["ps", "--all"], timeout=60)
        logs = session.run_command("l4-03-compose-logs", compose + ["logs", "--no-color"], timeout=120)
        session.append_docker_status(project, status.output)
        session.append_docker_logs(project, logs.output)
    finally:
        session.run_command(
            "l4-03-compose-down",
            compose + ["down", "--volumes", "--remove-orphans", "--rmi", "local"],
            timeout=180,
        )
    record_workspace_isolation(session)
