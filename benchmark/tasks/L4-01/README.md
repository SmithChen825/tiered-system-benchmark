# L4-01 Removed-Column Schema Cascade

This researcher-facing package implements the representative Level 4 pilot task. The evaluated system receives only a fresh copy of `fixture_repo/` and the complete `public_task_brief.md`.

The fixture contains three services:

- Vue 3 frontend at `http://127.0.0.1:8080`;
- FastAPI and SQLAlchemy backend at `http://127.0.0.1:8000`;
- PostgreSQL 16.6 database on the internal Compose network.

The database starts in the intended post-migration state: `users.age` is absent. Stale downstream references remain in the SQLAlchemy model, Pydantic response schema, and Vue table. The repair must remove those references while preserving the database state; re-adding `age` is explicitly invalid.

Package separation:

- `fixture_repo/`: faulty three-service repository visible to the agent;
- `public_task_brief.md`: frozen complete brief;
- `evaluator/hidden_tests/`: evaluator-only architectural and browser checks;
- `oracle/`: known-good multi-file repair outside the agent workspace;
- `scripts/`: reset, oracle, contract, and Compose validation utilities.

## Locked service images

- PostgreSQL: `postgres:16.6-alpine@sha256:1d04b9ba1d4996401f2552b51beda8187f175c0645c091e4781134fc9c9a3eef`
- Python: `python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0`
- Node builder: `node:22.12.0-alpine@sha256:51eff88af6dff26f59316b6e356188ffa2c422bd3c3b76f2556a2e7e89d080bd`
- Frontend Nginx: `nginx:1.27.3-alpine@sha256:814a8e88df978ade80e584cc5b333144b9372a8e3c98872d07137dbf3b44d0e4`

The most recent evidence is recorded in `validation_report.md`. Reproduce the source/reset checks with `scripts/validate_cycle.py` and the database/API/browser checks with `scripts/validate_compose.py`.
