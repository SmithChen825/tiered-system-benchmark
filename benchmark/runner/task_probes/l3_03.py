from __future__ import annotations

from .common import ProbeSession, record_workspace_isolation, run_manifest_pytests
from .main_common import run_compose_browser_check


def run(session: ProbeSession) -> None:
    run_manifest_pytests(session)
    run_compose_browser_check(
        session,
        project_prefix="tsbprobe-l303-",
        observation_ids=["browser_reset_network"],
        expected_mode="working",
    )
    record_workspace_isolation(session)
