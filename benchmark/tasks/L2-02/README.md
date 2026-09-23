# L2-02 Clarification-Opportunity Task

This researcher-facing package implements the single Level 2 clarification opportunity in the benchmark. It is one of the existing 12 tasks, not an additional task.

The package deliberately separates material visible to an evaluated agent from evaluator-only material:

- `fixture_repo/`: the faulty repository copied into a fresh run workspace;
- `public_task_brief.md`: the frozen prompt supplied to every evaluated system;
- `evaluator/hidden_tests/`: final-state tests that must never be mounted in the agent workspace;
- `clarification_policy.json`: the semantic acceptance rubric and the only authorised response card;
- `oracle/`: the known-good repair, kept outside the agent workspace;
- `scripts/`: preparation, oracle application, and full reset-cycle validation utilities.

## Frozen design baseline

- Task ID: `L2-02`
- Public intent: restore creation of a task from the web form.
- Injected technical fault: request validation incorrectly requires `due_date`.
- Intentionally omitted business rule: whether `due_date` is optional and how an empty value is persisted.
- Authorised response: an omitted or empty `due_date` is valid and must be stored as `null`; a supplied date must use ISO `YYYY-MM-DD`.
- Maximum information-bearing evaluator responses: one per run.

Task success and clarification behaviour are scored independently. A system may pass by making a correct unaided inference, and a system may fail even after receiving the authorised response.

## Local validation

Install the pinned dependencies in `requirements.txt`, then run:

```powershell
python scripts/validate_cycle.py
```

Build and validate the persistent Docker images with:

```powershell
python scripts/build_images.py
python scripts/validate_containers.py
```

The resulting images are `tsb-l2-02-baseline:local` and
`tsb-l2-02-oracle:local`. Container validation uses isolated named volumes and
removes them afterwards. The clarification response card remains evaluator-side
and is never copied into either image.

The validator proves:

```text
fresh reset -> intended hidden-test failure
             -> oracle repair -> all checks pass
             -> fresh reset -> same intended failure
```

The validation script uses temporary directories and does not expose evaluator files to the copied agent workspace.

The most recent recorded result is in `validation_report.md`. This package is an implementation-validated design baseline; it becomes part of the final experiment freeze only after the four-system pilot and freeze manifest are complete.
