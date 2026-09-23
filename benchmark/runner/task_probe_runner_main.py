from __future__ import annotations

import argparse
import importlib
from pathlib import Path

from .common import load_json
from .task_probes.common import (
    CommandOutcome,
    InfrastructureProbeError,
    ProbeSession,
    write_observations,
)


class MainProbeSession(ProbeSession):
    def run_command(
        self,
        label: str,
        command: list[str],
        *,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
        timeout: int = 180,
    ) -> CommandOutcome:
        return super().run_command(
            label,
            command,
            cwd=cwd,
            environment=environment,
            timeout=min(timeout, 180),
        )


def run_task_probes(evidence_directory: Path, workspace: Path, output_path: Path) -> dict:
    session = MainProbeSession(evidence_directory, workspace)
    try:
        module_name = session.task_id.lower().replace("-", "_")
        module = importlib.import_module(f"{__package__}.task_probes.{module_name}")
        module.run(session)
        value = session.result()
    except InfrastructureProbeError as error:
        value = session.result(
            evaluation_error={"classification": "infrastructure_failure", "detail": str(error)}
        )
    except Exception as error:
        value = session.result(
            evaluation_error={
                "classification": "evaluator_error",
                "detail": f"{type(error).__name__}: {error}",
            }
        )
    write_observations(output_path.resolve(), value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a main-experiment task's frozen probes and write observations."
    )
    parser.add_argument("evidence_directory", type=Path)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    value = run_task_probes(arguments.evidence_directory, arguments.workspace, arguments.output)
    metadata = load_json(arguments.evidence_directory / "metadata.json")
    print(f"run_id={metadata['run_id']}")
    print(f"task_id={metadata['task']['task_id']}")
    print(f"observation_count={len(value['observations'])}")
    print(f"evaluation_error={value['evaluation_error']}")
    print(f"output={arguments.output.resolve()}")


if __name__ == "__main__":
    main()
