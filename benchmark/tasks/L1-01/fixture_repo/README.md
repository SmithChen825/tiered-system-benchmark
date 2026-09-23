# Northstar Supply Catalogue

A static product catalogue served by Nginx.

## Run with Docker Compose

```powershell
docker compose up --build
```

Open `http://127.0.0.1:8080/`.

## Available tests

```powershell
python -m pytest -q
```

Repository tests check the page structure. Final evaluation may also use evaluator-only filesystem, HTTP, and browser checks.
