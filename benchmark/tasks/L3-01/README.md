# L3-01 Frontend-to-Backend CORS Repair

This researcher-facing package implements the representative Level 3 pilot task. The evaluated system receives only a fresh copy of `fixture_repo/` and the complete `public_task_brief.md`.

The fixture is a two-service application:

- a Vue 3 frontend served by Nginx at the frozen browser origin `http://127.0.0.1:8080`;
- a FastAPI backend at `http://127.0.0.1:8000`.

The backend endpoint is healthy and returns valid account data, but its CORS policy names the stale development origin `http://127.0.0.1:5173`. A browser therefore blocks the frontend request. The repair must name the frozen frontend origin exactly; a wildcard is not accepted.

Package separation:

- `fixture_repo/`: faulty Vue–FastAPI repository visible to the agent;
- `public_task_brief.md`: frozen complete brief with no clarification opportunity;
- `evaluator/hidden_tests/`: evaluator-only contract and browser checks;
- `oracle/`: known-good repair outside the agent workspace;
- `scripts/`: reset, oracle, and validation utilities.

## Locked service images

- Python: `python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0`
- Node builder: `node:22.12.0-alpine@sha256:51eff88af6dff26f59316b6e356188ffa2c422bd3c3b76f2556a2e7e89d080bd`
- Frontend Nginx: `nginx:1.27.3-alpine@sha256:814a8e88df978ade80e584cc5b333144b9372a8e3c98872d07137dbf3b44d0e4`

The final experiment-freeze manifest must additionally record the built service-image IDs and the exact Vue/Vite lockfile hash.

The most recent implementation evidence is recorded in `validation_report.md` and can be reproduced with `scripts/validate_cycle.py` followed by `scripts/validate_compose.py`.
