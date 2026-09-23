from __future__ import annotations

import argparse
import shutil
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = TASK_ROOT / "fixture_repo"


def prepare_run(destination: Path) -> Path:
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing run workspace: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE, destination)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy the frozen L2-02 faulty fixture into a new run workspace."
    )
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    created = prepare_run(arguments.destination)
    print(created)


if __name__ == "__main__":
    main()
