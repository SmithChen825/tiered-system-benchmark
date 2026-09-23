from __future__ import annotations

import argparse
import shutil
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
ORACLE_SCHEMA = TASK_ROOT / "oracle" / "app" / "schemas.py"


def apply_oracle(repository: Path) -> Path:
    repository = repository.resolve()
    target = repository / "app" / "schemas.py"
    if not (repository / "app" / "main.py").is_file() or not target.is_file():
        raise ValueError(f"Not an L2-02 repository workspace: {repository}")
    shutil.copy2(ORACLE_SCHEMA, target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply the researcher-authored L2-02 oracle repair."
    )
    parser.add_argument("repository", type=Path)
    arguments = parser.parse_args()
    changed = apply_oracle(arguments.repository)
    print(changed)


if __name__ == "__main__":
    main()
