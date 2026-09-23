from __future__ import annotations

import argparse
import shutil
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
ORACLE_INDEX = TASK_ROOT / "oracle" / "site" / "index.html"


def apply_oracle(repository: Path) -> Path:
    repository = repository.resolve()
    target = repository / "site" / "index.html"
    if not (repository / "nginx.conf").is_file() or not target.is_file():
        raise ValueError(f"Not an L1-03 repository workspace: {repository}")
    shutil.copy2(ORACLE_INDEX, target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply the researcher-authored L1-03 oracle repair."
    )
    parser.add_argument("repository", type=Path)
    arguments = parser.parse_args()
    print(apply_oracle(arguments.repository))


if __name__ == "__main__":
    main()

