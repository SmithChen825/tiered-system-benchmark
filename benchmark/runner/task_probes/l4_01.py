from __future__ import annotations

import json
import os
import sys

from .common import (
    InfrastructureProbeError,
    ProbeSession,
    record_workspace_isolation,
    require_docker,
    resolve_node_environment,
    run_manifest_pytests,
)


MANUAL_SOURCE_IDS = {
    "browser_user_table_loads",
    "compose_service_health",
    "runtime_age_column_count",
    "runtime_columns_and_row_count",
    "users_api_returns_remaining_contract",
}


USERS_SCRIPT = r"""
import json
import urllib.error
import urllib.request
request = urllib.request.Request(
    "http://127.0.0.1:8000/api/users",
    headers={"Origin": "http://127.0.0.1:8080"},
)
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        status = response.status
        body = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as error:
    status = error.code
    body = error.read().decode("utf-8", errors="replace")
print(json.dumps({"status": status, "body": body}))
"""


def _database_query(
    session: ProbeSession,
    compose: list[str],
    label: str,
    sql: str,
):
    return session.run_command(
        label,
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
        timeout=60,
    )


def run(session: ProbeSession) -> None:
    docker = require_docker(session)
    node, node_environment = resolve_node_environment()
    playwright = session.run_command(
        "l4-playwright-runtime",
        [node, "-e", "require('playwright'); console.log('playwright=ready')"],
        environment=node_environment,
        timeout=30,
    )
    if playwright.returncode != 0:
        raise InfrastructureProbeError("Playwright is unavailable: " + playwright.output)

    run_manifest_pytests(session)
    record_workspace_isolation(session)

    project = f"tsbl401probe{os.getpid()}"
    compose = [
        docker,
        "compose",
        "-p",
        project,
        "-f",
        str(session.workspace / "compose.yaml"),
    ]
    up = session.run_command(
        "l4-compose-up",
        compose + ["up", "--build", "--detach", "--wait", "--wait-timeout", "180"],
        timeout=480,
    )
    session.record(
        "compose_service_health",
        "passed" if up.returncode == 0 else "failed",
        duration_seconds=up.duration_seconds,
        detail=None if up.returncode == 0 else "Compose services did not become healthy.",
        evidence=[up.evidence_path],
    )

    age_passed = False
    shape_passed = False
    users_passed = False
    database_details: dict[str, object] = {}
    try:
        if up.returncode == 0:
            age = _database_query(
                session,
                compose,
                "l4-db-age-column",
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='users' AND column_name='age';",
            )
            columns = _database_query(
                session,
                compose,
                "l4-db-columns",
                "SELECT string_agg(column_name, ',' ORDER BY ordinal_position) "
                "FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='users';",
            )
            rows = _database_query(
                session,
                compose,
                "l4-db-rows",
                "SELECT COUNT(*) FROM users;",
            )
            age_passed = age.returncode == 0 and age.output.strip() == "0"
            shape_passed = bool(
                columns.returncode == 0
                and columns.output.strip() == "id,name,email,role"
                and rows.returncode == 0
                and rows.output.strip() == "3"
            )
            session.record(
                "runtime_age_column_count",
                "passed" if age_passed else "failed",
                duration_seconds=age.duration_seconds,
                detail=None if age_passed else f"Observed age-column query: {age.output.strip()!r}",
                evidence=[age.evidence_path],
            )
            session.record(
                "runtime_columns_and_row_count",
                "passed" if shape_passed else "failed",
                duration_seconds=columns.duration_seconds + rows.duration_seconds,
                detail=(
                    None
                    if shape_passed
                    else f"columns={columns.output.strip()!r}; rows={rows.output.strip()!r}"
                ),
                evidence=[columns.evidence_path, rows.evidence_path],
            )
            database_details = {
                "age_column_count": age.output.strip(),
                "columns": columns.output.strip(),
                "row_count": rows.output.strip(),
            }

            users = session.run_command(
                "l4-users-api",
                [sys.executable, "-c", USERS_SCRIPT],
                timeout=30,
            )
            payload = None
            if users.returncode == 0:
                try:
                    payload = json.loads(users.output)
                except json.JSONDecodeError:
                    pass
            body = payload.get("body") if isinstance(payload, dict) else None
            users_passed = bool(
                isinstance(payload, dict)
                and payload.get("status") == 200
                and isinstance(body, list)
                and len(body) == 3
                and all(
                    isinstance(item, dict)
                    and set(item) == {"id", "name", "email", "role"}
                    for item in body
                )
            )
            session.record(
                "users_api_returns_remaining_contract",
                "passed" if users_passed else "failed",
                duration_seconds=users.duration_seconds,
                detail=None if users_passed else f"Unexpected users response: {payload!r}",
                evidence=[users.evidence_path],
            )

            browser = session.run_command(
                "l4-browser-user-table",
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
            session.record_command("browser_user_table_loads", browser)
        else:
            for observation_id, detail in (
                ("runtime_age_column_count", "Database query unavailable because Compose startup failed."),
                ("runtime_columns_and_row_count", "Database query unavailable because Compose startup failed."),
                ("users_api_returns_remaining_contract", "API unavailable because Compose startup failed."),
                ("browser_user_table_loads", "Browser contract unavailable because Compose startup failed."),
            ):
                session.record(
                    observation_id,
                    "failed",
                    detail=detail,
                    evidence=[up.evidence_path],
                )

        status = session.run_command(
            "l4-compose-status", compose + ["ps", "--all"], timeout=60
        )
        logs = session.run_command(
            "l4-compose-logs", compose + ["logs", "--no-color"], timeout=120
        )
        session.append_docker_status(project, status.output)
        session.append_docker_logs(project, logs.output)
    finally:
        session.run_command(
            "l4-compose-down",
            compose + ["down", "--volumes", "--remove-orphans", "--rmi", "local"],
            timeout=180,
        )

    session.database_checks = {
        "status": "completed" if up.returncode == 0 else "failed",
        "checks": [
            {"id": "runtime_age_column_count", "passed": age_passed},
            {"id": "runtime_columns_and_row_count", "passed": shape_passed},
        ],
        "details": database_details,
    }
