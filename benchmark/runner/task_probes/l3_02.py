from __future__ import annotations

from .common import ProbeSession, record_workspace_isolation, run_manifest_pytests
from .main_common import run_compose_browser_check


def run(session: ProbeSession) -> None:
    run_manifest_pytests(session)
    run_compose_browser_check(
        session,
        project_prefix="tsbprobe-l302-",
        observation_ids=["browser_order_status"],
        expected_mode="loaded",
    )
    record_workspace_isolation(session)
