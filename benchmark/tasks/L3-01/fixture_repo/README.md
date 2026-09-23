# Account Portal

A two-service Vue and FastAPI application.

## Run

```powershell
docker compose up --build
```

- Frontend: `http://127.0.0.1:8080`
- Backend health: `http://127.0.0.1:8000/health`
- Backend account endpoint: `http://127.0.0.1:8000/api/account`

## Available backend tests

```powershell
python -m pip install -r backend/requirements.txt
python -m pytest -q backend/tests
```

These are direct API smoke tests. Final evaluation may include evaluator-only CORS and real-browser checks.
