from __future__ import annotations

import argparse
import shutil
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
ORACLE_MAIN = TASK_ROOT / "oracle" / "app" / "main.py"


def apply_oracle(repository: Path) -> Path:
    repository = repository.resolve()
    target = repository / "app" / "main.py"
    if not (repository / "app" / "main.py").is_file() or not target.is_file():
        raise ValueError(f"Not an L2-01 repository workspace: {repository}")
    shutil.copy2(ORACLE_MAIN, target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply the researcher-authored L2-01 oracle repair."
    )
    parser.add_argument("repository", type=Path)
    arguments = parser.parse_args()
    changed = apply_oracle(arguments.repository)
    print(changed)


if __name__ == "__main__":
    main()
