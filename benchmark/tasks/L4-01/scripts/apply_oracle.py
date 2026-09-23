from __future__ import annotations

import argparse
import shutil
from pathlib import Path


TASK_ROOT = Path(__file__).resolve().parents[1]
ORACLE_ROOT = TASK_ROOT / "oracle"
REPLACEMENTS = (
    (ORACLE_ROOT / "backend" / "app" / "models.py", Path("backend/app/models.py")),
    (ORACLE_ROOT / "backend" / "app" / "schemas.py", Path("backend/app/schemas.py")),
    (ORACLE_ROOT / "frontend" / "src" / "App.vue", Path("frontend/src/App.vue")),
)


def apply_oracle(repository: Path) -> list[Path]:
    repository = repository.resolve()
    if not (repository / "compose.yaml").is_file():
        raise ValueError(f"Not an L4-01 repository workspace: {repository}")
    changed = []
    for source, relative_target in REPLACEMENTS:
        target = repository / relative_target
        if not target.is_file():
            raise ValueError(f"Missing oracle target: {target}")
        shutil.copy2(source, target)
        changed.append(target)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply the researcher-authored L4-01 multi-file oracle repair."
    )
    parser.add_argument("repository", type=Path)
    arguments = parser.parse_args()
    for changed in apply_oracle(arguments.repository):
        print(changed)


if __name__ == "__main__":
    main()
