from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


FIXED_AUTHOR_NAME = "TSB Fixture Builder"
FIXED_AUTHOR_EMAIL = "tsb-fixture@local.invalid"
FIXED_COMMIT_DATE = "2026-08-06T00:00:00+00:00"


def find_git() -> str:
    executable = shutil.which("git")
    if not executable:
        raise RuntimeError("Git executable not found")
    return executable


def _run_git(
    repository: Path,
    arguments: list[str],
    *,
    environment: dict[str, str] | None = None,
) -> str:
    completed = subprocess.run(
        [find_git(), *arguments],
        cwd=repository,
        env=environment or os.environ.copy(),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Git command failed ({completed.returncode}): "
            f"git {' '.join(arguments)}\n{completed.stdout}"
        )
    return completed.stdout.strip()


def initialize_start_commit(repository: Path, task_id: str) -> str:
    repository = repository.resolve()
    if not repository.is_dir():
        raise FileNotFoundError(f"Workspace repository does not exist: {repository}")
    if (repository / ".git").exists():
        raise FileExistsError(f"Workspace already contains Git metadata: {repository}")

    _run_git(repository, ["init", "--quiet", "--initial-branch=main"])
    _run_git(repository, ["config", "core.autocrlf", "false"])
    _run_git(repository, ["config", "core.filemode", "false"])
    _run_git(repository, ["config", "commit.gpgSign", "false"])
    _run_git(repository, ["add", "--all"])

    commit_environment = os.environ.copy()
    commit_environment.update(
        {
            "GIT_AUTHOR_NAME": FIXED_AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": FIXED_AUTHOR_EMAIL,
            "GIT_AUTHOR_DATE": FIXED_COMMIT_DATE,
            "GIT_COMMITTER_NAME": FIXED_AUTHOR_NAME,
            "GIT_COMMITTER_EMAIL": FIXED_AUTHOR_EMAIL,
            "GIT_COMMITTER_DATE": FIXED_COMMIT_DATE,
        }
    )
    _run_git(
        repository,
        [
            "commit",
            "--quiet",
            "--no-gpg-sign",
            "--no-verify",
            "--message",
            f"TSB frozen start state: {task_id}",
        ],
        environment=commit_environment,
    )
    commit = _run_git(repository, ["rev-parse", "HEAD"])
    if len(commit) != 40:
        raise RuntimeError(f"Unexpected Git commit identifier: {commit}")
    if _run_git(repository, ["status", "--porcelain"]):
        raise RuntimeError("Deterministic start commit left a dirty workspace")
    return commit


def inspect_start_commit(repository: Path) -> tuple[str, bool]:
    repository = repository.resolve()
    if not (repository / ".git").is_dir():
        raise FileNotFoundError(f"Workspace has no Git repository: {repository}")
    commit = _run_git(repository, ["rev-parse", "HEAD"])
    clean = not bool(_run_git(repository, ["status", "--porcelain"]))
    return commit, clean


def start_commit_exists(repository: Path, commit: str) -> bool:
    try:
        _run_git(repository.resolve(), ["cat-file", "-e", f"{commit}^{{commit}}"])
    except (FileNotFoundError, RuntimeError):
        return False
    return True
