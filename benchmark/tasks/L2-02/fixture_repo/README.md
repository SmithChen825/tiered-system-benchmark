# Task Board

A minimal FastAPI task-board application with an HTML form and SQLite persistence.

## Setup

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/` to use the task-creation form.

## Docker

The repository also contains a pinned Docker environment. To start the faulty
baseline with an isolated SQLite volume:

```powershell
docker compose up --build --wait
```

Remove the container and its database volume after a run with:

```powershell
docker compose down --volumes
```

## Available tests

```powershell
python -m pytest -q
```

These repository tests are smoke tests only. Final evaluation may include evaluator-only tests that are not available in the task workspace.
