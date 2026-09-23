from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

try:
    from .common import REPOSITORY_ROOT, TASKS_ROOT, load_json
    from .git_start_state import initialize_start_commit
except ImportError:  # Supports direct script execution.
    from common import REPOSITORY_ROOT, TASKS_ROOT, load_json  # type: ignore
    from git_start_state import initialize_start_commit  # type: ignore


def compute_start_commit(task_id: str, temporary_parent: Path) -> str:
    task_root = TASKS_ROOT / task_id
    fixture = task_root / "fixture_repo"
    if not fixture.is_dir():
        raise FileNotFoundError(f"Missing fixture for {task_id}: {fixture}")
    with tempfile.TemporaryDirectory(
        prefix=f"{task_id.lower()}-start-commit-", dir=temporary_parent
    ) as temporary:
        repository = Path(temporary) / "repo"
        shutil.copytree(fixture, repository)
        return initialize_start_commit(repository, task_id)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recompute deterministic TSB fixture start commits."
    )
    parser.add_argument("task_ids", nargs="*")
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    task_ids = arguments.task_ids or [path.name for path in sorted(TASKS_ROOT.glob("L*-*"))]
    temporary_parent = REPOSITORY_ROOT / "tmp"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    mismatches = 0
    for task_id in task_ids:
        observed = compute_start_commit(task_id, temporary_parent)
        manifest = load_json(TASKS_ROOT / task_id / "fixture_manifest.json")
        expected = manifest.get("start_commit")
        status = "MATCH" if observed == expected else "DIFFERS"
        print(f"{task_id} start_commit={observed} manifest={expected} status={status}")
        mismatches += int(observed != expected)
    if arguments.verify and mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
