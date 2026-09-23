# L4-03 Service Startup and Dashboard Health

Deterministic Level 4 task: the backend database URL names a host that is absent from the Compose network. The FastAPI lifespan requires a real PostgreSQL connection, so the backend cannot become healthy. The oracle changes only the database hostname in `compose.yaml`. Validate with `python scripts/validate_cycle.py`, then run the PostgreSQL/Compose/Chromium validation.

