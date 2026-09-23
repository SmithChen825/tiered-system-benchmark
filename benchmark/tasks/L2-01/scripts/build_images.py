from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from apply_oracle import apply_oracle
from prepare_run import FIXTURE, prepare_run


TASK_ROOT = Path(__file__).resolve().parents[1]
VALIDATION_TEMP_PARENT = TASK_ROOT.parents[2] / "tmp"
BASELINE_IMAGE = "tsb-l2-01-baseline:local"
ORACLE_IMAGE = "tsb-l2-01-oracle:local"


def run(command: list[str], *, cwd: Path, timeout: int = 600) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stdout}"
        )
    print(completed.stdout.strip())


def build_images() -> None:
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker CLI not found")

    VALIDATION_TEMP_PARENT.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix="l2-01-oracle-image-", dir=VALIDATION_TEMP_PARENT)
    )
    try:
        print(f"[1/2] Building {BASELINE_IMAGE}", flush=True)
        run([docker, "build", "--tag", BASELINE_IMAGE, str(FIXTURE)], cwd=FIXTURE)

        oracle_repository = prepare_run(temporary_root / "repository")
        apply_oracle(oracle_repository)
        print(f"[2/2] Building {ORACLE_IMAGE}", flush=True)
        run(
            [docker, "build", "--tag", ORACLE_IMAGE, str(oracle_repository)],
            cwd=oracle_repository,
        )
        print("L2-01 image build: PASS")
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == "__main__":
    build_images()
