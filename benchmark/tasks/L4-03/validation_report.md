# L4-03 Validation Report

Validated 2026-08-29. Both fresh resets failed exactly `test_database_url_targets_the_frozen_compose_service`. The researcher-authored oracle changed only the backend hostname in `compose.yaml` from `postgres` to the frozen `db` service and passed all six hidden checks.

The baseline Compose stack created the PostgreSQL schema with all three seeded dashboard metrics, but the FastAPI container exited during its lifespan database connection. The frontend remained healthy, requested the direct dashboard API, received no response, and Chromium rendered `Dashboard unavailable.` With the oracle, all three services passed their Compose health checks; `/health` returned `status=ok` and `database=reachable`; `/api/dashboard` returned the frozen operational status and three PostgreSQL-backed metrics; and Chromium rendered the same data. Fixture SHA-256: `b39d8d8e9e37edb9c6fece35aa352f598dd98d0942d9eda97523d1d7314fd6b9`.

Result: **PASS**.

