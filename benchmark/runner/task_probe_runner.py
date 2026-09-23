from __future__ import annotations

import argparse
from pathlib import Path

from .common import load_json
from .task_probes.common import (
    InfrastructureProbeError,
    ProbeSession,
    write_observations,
)


def run_task_probes(
    evidence_directory: Path,
    workspace: Path,
    output_path: Path,
) -> dict:
    session = ProbeSession(evidence_directory, workspace)
    try:
        if session.task_id == "L1-01":
            from .task_probes.l1_01 import run
        elif session.task_id == "L2-02":
            from .task_probes.l2_02 import run
        elif session.task_id == "L3-01":
            from .task_probes.l3_01 import run
        elif session.task_id == "L4-01":
            from .task_probes.l4_01 import run
        else:
            raise RuntimeError(f"No task probe adapter for {session.task_id}")
        run(session)
        value = session.result()
    except InfrastructureProbeError as error:
        value = session.result(
            evaluation_error={
                "classification": "infrastructure_failure",
                "detail": str(error),
            }
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
        description="Run a representative task's frozen probes and write observations."
    )
    parser.add_argument("evidence_directory", type=Path)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    value = run_task_probes(
        arguments.evidence_directory, arguments.workspace, arguments.output
    )
    metadata = load_json(arguments.evidence_directory / "metadata.json")
    print(f"run_id={metadata['run_id']}")
    print(f"task_id={metadata['task']['task_id']}")
    print(f"observation_count={len(value['observations'])}")
    print(f"evaluation_error={value['evaluation_error']}")
    print(f"output={arguments.output.resolve()}")


if __name__ == "__main__":
    main()
