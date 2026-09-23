# Shared run and evidence framework

Start with the repository's [local validation guide](../../docs/reproduction.md).

| Module | Responsibility |
|---|---|
| `create_run.py` | Prepare an isolated fixture and separate evidence directory |
| `api_wrapper/` | Model turns, logical actions, context retention, transport adapters, stopping rules |
| `native_ide_run_recorder.py` | Native timing, permission/clarification events, and final-state freeze |
| `task_probes/` | Task-specific integration evidence collection |
| `structured_evaluator.py` | Bind observations to functional and architectural checks |
| `evaluator_finalizer.py` | Finalize terminal outcome, evidence, and diff |
| `evidence_validator.py` | Validate the stored evidence without repairing it |
| `verify_start_commits.py` | Recompute all deterministic fixture commits |

Detailed contracts live in [benchmark/docs](../docs). Formal paid execution requires deployment-specific records not included in this curated export.
