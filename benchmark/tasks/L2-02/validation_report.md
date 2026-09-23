# L2-02 Validation Report

- Validation date: 2026-08-08
- Host platform: Windows
- Evaluator runtime: Python 3.12.8 container, pytest 8.3.4
- Dependency set: pinned in `requirements.txt`
- Fixture SHA-256: `1e2d1900edb5e5fa95b4b3a3053522e46599995a5d7b5237e7489f7639b01748`
- Container base: `python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0`
- Baseline image: `tsb-l2-02-baseline:local` (`sha256:1075bbf62c01fb8cb7e15f1ad9628f1e6e0d0c3455ab4795cc7d43df8f425560`)
- Oracle image: `tsb-l2-02-oracle:local` (`sha256:e02e0cdf855e4686742262dd6845754f1d8ffaf3f8d370b702d49d4db7cb44e6`)

## Checks completed

1. All researcher-facing JSON files parse successfully.
2. The two agent-visible smoke tests pass in the faulty fixture.
3. A fresh copy of the fixture fails exactly the intended evaluator tests:
   - `test_omitted_due_date_is_accepted_and_persisted_as_null`;
   - `test_empty_due_date_is_accepted_and_persisted_as_null`;
   - `test_created_task_survives_application_restart`.
4. The researcher-authored oracle repair passes all eight evaluator-only hidden tests in the 2026-08-08 validation suite.
5. A second independent reset reproduces the same fixture hash and the same three failures.
6. `oracle/oracle.patch` passes `git apply --check` against the faulty fixture.
7. The pinned baseline and oracle Docker images build successfully and run as an unprivileged user.
8. Container-level HTTP checks reproduce the baseline 422 responses for omitted/empty `due_date`; a supplied ISO date remains accepted.
9. The oracle container accepts omitted/empty `due_date`, persists both as SQLite `NULL`, preserves supplied-date validation, and rejects malformed dates.
10. SQLite state survives a container restart when the named volume is retained.
11. A fresh named volume restores an empty database, and all validation containers and temporary volumes are removed after the check.

## Result

```text
L2-02 validation cycle: PASS
baseline failure: reproducible
oracle hidden tests: PASS
second reset same failure: PASS
baseline container fault: PASS
oracle container HTTP and persistence: PASS
container restart: PASS
clean volume reset: PASS
```

This result validates the task implementation and reset cycle. It does not yet constitute the final experiment freeze; versions, system prompts, adapters, task-level time limit, run schedule, and the complete four-system pilot remain to be frozen separately.

## Evaluator-classification addendum (2026-08-08)

The approved evaluator manifest maps seven functional tests and six architectural
invariants separately. One static invariant check was added to reject hard-coded
evaluator examples or replacement ISO dates. The complete reset/oracle hidden-test
cycle, image builds, HTTP behaviour, SQLite restart persistence, and clean-volume
reset were rerun successfully on 2026-08-08. The post-change revalidation gate is
therefore cleared.
