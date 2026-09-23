from __future__ import annotations

from .common import ProbeSession, record_workspace_isolation, run_manifest_pytests


def run(session: ProbeSession) -> None:
    run_manifest_pytests(session)
    record_workspace_isolation(session)
