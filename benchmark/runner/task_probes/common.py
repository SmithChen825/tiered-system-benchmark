from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..common import (
    BANNED_WORKSPACE_NAMES,
    REPOSITORY_ROOT,
    TASKS_ROOT,
    load_json,
    write_json,
)


PROBE_VERSION = "task-probes/0.1.0"


class InfrastructureProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandOutcome:
    returncode: int
    output: str
    duration_seconds: float
    evidence_path: str


class ProbeSession:
    def __init__(self, evidence_directory: Path, workspace: Path) -> None:
        self.evidence_directory = evidence_directory.resolve()
        self.workspace = workspace.resolve()
        metadata = load_json(self.evidence_directory / "metadata.json")
        self.task_id = metadata["task"]["task_id"]
        self.task_root = TASKS_ROOT / self.task_id
        self.manifest = load_json(self.task_root / "evaluator_manifest.json")
        self.log_directory = self.evidence_directory / "evaluator" / "probes"
        self.log_directory.mkdir(parents=True, exist_ok=True)
        self.observations: dict[str, dict[str, Any]] = {}
        self.docker_status_parts: list[str] = []
        self.docker_log_parts: list[str] = []
        self.database_checks: dict[str, Any] = {"status": "not_applicable", "checks": []}

    def record(
        self,
        observation_id: str,
        status: str,
        *,
        duration_seconds: float | None = None,
        detail: str | None = None,
        evidence: list[str] | None = None,
    ) -> None:
        if observation_id in self.observations:
            raise RuntimeError(f"Duplicate probe observation: {observation_id}")
        self.observations[observation_id] = {
            "id": observation_id,
            "status": status,
            "duration_seconds": duration_seconds,
            "detail": detail,
            "evidence": evidence or [],
        }

    def run_command(
        self,
        label: str,
        command: list[str],
        *,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
        timeout: int = 180,
    ) -> CommandOutcome:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd or self.workspace,
                env=environment or os.environ.copy(),
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            output = completed.stdout
            returncode = completed.returncode
        except subprocess.TimeoutExpired as error:
            output = (error.stdout or "") + f"\nProbe command timed out after {timeout}s.\n"
            returncode = 124
        except OSError as error:
            raise InfrastructureProbeError(
                f"Cannot execute probe command {command[0]!r}: {error}"
            ) from error
        duration = time.monotonic() - started
        log_path = self.log_directory / f"{label}.log"
        log_path.write_text(
            f"command={command!r}\nreturncode={returncode}\n\n{output}",
            encoding="utf-8",
        )
        relative = log_path.relative_to(self.evidence_directory).as_posix()
        return CommandOutcome(returncode, output, duration, relative)

    def record_command(self, observation_id: str, outcome: CommandOutcome) -> None:
        self.record(
            observation_id,
            "passed" if outcome.returncode == 0 else "failed",
            duration_seconds=outcome.duration_seconds,
            detail=None if outcome.returncode == 0 else _last_output(outcome.output),
            evidence=[outcome.evidence_path],
        )

    def append_docker_status(self, label: str, output: str) -> None:
        self.docker_status_parts.append(f"[{label}]\n{output.strip()}\n")

    def append_docker_logs(self, label: str, output: str) -> None:
        self.docker_log_parts.append(f"[{label}]\n{output.strip()}\n")

    def result(self, *, evaluation_error: dict[str, str] | None = None) -> dict[str, Any]:
        observations = [] if evaluation_error else list(self.observations.values())
        return {
            "schema_version": "1.0.0",
            "evaluator_version": PROBE_VERSION,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "observations": observations,
            "docker_status": "\n".join(self.docker_status_parts),
            "docker_logs": "\n".join(self.docker_log_parts),
            "database_checks": self.database_checks,
            "evaluation_error": evaluation_error,
        }


def _last_output(output: str, maximum: int = 1200) -> str:
    stripped = output.strip()
    return stripped[-maximum:] if stripped else "Probe command returned non-zero."


def resolve_node_environment() -> tuple[str, dict[str, str]]:
    environment = os.environ.copy()
    bundled_root = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
    )
    node = environment.get("NODE_EXE") or shutil.which("node")
    if not node:
        candidate = bundled_root / "bin" / "node.exe"
        if candidate.is_file():
            node = str(candidate)
    if not node:
        raise InfrastructureProbeError("Node.js is unavailable for browser probes")
    if not environment.get("NODE_PATH"):
        modules = bundled_root / "node_modules"
        if modules.is_dir():
            environment["NODE_PATH"] = str(modules)
    if not environment.get("BROWSER_EXE"):
        browser_candidates = (
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        )
        browser = next((path for path in browser_candidates if path.is_file()), None)
        if browser:
            environment["BROWSER_EXE"] = str(browser)
    return node, environment


def resolve_pytest_python() -> str:
    candidates: list[Path] = []
    configured = os.environ.get("PYTEST_PYTHON")
    if configured:
        candidates.append(Path(configured))
    candidates.append(Path(sys.executable))
    candidates.append(REPOSITORY_ROOT / "tmp" / "l2-02-venv" / "Scripts" / "python.exe")
    checked: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in checked or not candidate.is_file():
            continue
        checked.add(candidate)
        completed = subprocess.run(
            [str(candidate), "-c", "import pytest"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode == 0:
            return str(candidate)
    raise InfrastructureProbeError(
        "No Python interpreter with pytest is available; set PYTEST_PYTHON"
    )


def require_docker(session: ProbeSession) -> str:
    docker = shutil.which("docker")
    if not docker:
        raise InfrastructureProbeError("Docker CLI is unavailable")
    outcome = session.run_command(
        "docker-engine",
        [docker, "version", "--format", "{{.Server.Version}}"],
        timeout=30,
    )
    if outcome.returncode != 0:
        raise InfrastructureProbeError(
            "Docker engine is unavailable: " + _last_output(outcome.output)
        )
    session.append_docker_status("engine", outcome.output)
    return docker


def manifest_pytest_sources(manifest: dict[str, Any]) -> dict[str, str]:
    sources: dict[str, str] = {}
    for item in manifest["functional_tests"]:
        if item["runner"] == "pytest":
            sources[item["id"]] = item["source"]
    for check in manifest["architecture_checks"]:
        for evidence in check["evidence"]:
            if evidence["source_id"] == "workspace_isolation":
                continue
            source = evidence["source"]
            if ".py::test_" in source:
                previous = sources.setdefault(evidence["source_id"], source)
                if previous != source:
                    raise RuntimeError(
                        f"Conflicting sources for {evidence['source_id']}: {previous}, {source}"
                    )
    return sources


def run_manifest_pytests(session: ProbeSession) -> None:
    sources = manifest_pytest_sources(session.manifest)
    environment = os.environ.copy()
    variable = session.manifest.get("pytest_environment_variable")
    if variable:
        environment[variable] = str(session.workspace)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    pytest_python = resolve_pytest_python()
    temporary_parent = REPOSITORY_ROOT / "tmp"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    for source_id, source in sources.items():
        path_text, node_id = source.split("::", maxsplit=1)
        node = f"{session.task_root / path_text}::{node_id}"
        with tempfile.TemporaryDirectory(
            prefix=f"probe-pytest-{session.task_id.lower()}-",
            dir=temporary_parent,
        ) as basetemp:
            outcome = session.run_command(
                f"pytest-{source_id}",
                [
                    pytest_python,
                    "-m",
                    "pytest",
                    "-q",
                    "--tb=short",
                    "-p",
                    "no:cacheprovider",
                    "--basetemp",
                    basetemp,
                    node,
                ],
                environment=environment,
                timeout=180,
            )
        session.record_command(source_id, outcome)


def record_workspace_isolation(session: ProbeSession) -> None:
    banned = {item.casefold() for item in BANNED_WORKSPACE_NAMES}
    violations: list[str] = []
    for path in session.workspace.rglob("*"):
        if path.name.casefold() in banned:
            violations.append(str(path))
        if path.is_symlink():
            violations.append(f"symlink:{path}")
    session.record(
        "workspace_isolation",
        "passed" if not violations else "failed",
        duration_seconds=0,
        detail=None if not violations else "; ".join(violations),
        evidence=["benchmark/runner/task_probes/common.py::record_workspace_isolation"],
    )


def write_observations(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, value)
