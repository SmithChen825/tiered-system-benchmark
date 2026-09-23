# User Directory

A Vue, FastAPI, and PostgreSQL application.

## Run

```powershell
docker compose up --build
```

- Frontend: `http://127.0.0.1:8080`
- Backend health: `http://127.0.0.1:8000/health`
- Users API: `http://127.0.0.1:8000/api/users`

## Available backend smoke test

```powershell
python -m pip install -r backend/requirements.txt
python -m pytest -q backend/tests
```

Final evaluation may include evaluator-only database-schema, API, and browser checks.
