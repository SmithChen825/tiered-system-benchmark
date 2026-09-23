from __future__ import annotations

from .common import ProbeSession, record_workspace_isolation, run_manifest_pytests
from .main_common import run_local_browser_check


def run(session: ProbeSession) -> None:
    run_manifest_pytests(session)
    run_local_browser_check(
        session,
        observation_id="mobile_navigation_chromium",
        expected_mode="usable",
    )
    record_workspace_isolation(session)
