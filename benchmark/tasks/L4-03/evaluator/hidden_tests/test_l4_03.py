import os
from pathlib import Path
import re


REPOSITORY = Path(os.environ["L4_03_REPO"]).resolve()
COMPOSE = REPOSITORY / "compose.yaml"
BACKEND_MAIN = REPOSITORY / "backend" / "app" / "main.py"
FRONTEND = REPOSITORY / "frontend" / "src" / "App.vue"


def test_database_url_targets_the_frozen_compose_service():
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "@db:5432/benchmark" in compose
    assert "@postgres:5432/benchmark" not in compose


def test_backend_lifespan_requires_database_connectivity():
    source = BACKEND_MAIN.read_text(encoding="utf-8")
    assert "@asynccontextmanager" in source
    assert "async def lifespan" in source
    before_yield = source.split("yield", 1)[0]
    assert "engine.connect()" in before_yield
    assert 'connection.execute(text("SELECT 1"))' in before_yield
    assert "lifespan=lifespan" in source


def test_health_and_dashboard_routes_remain_database_backed():
    source = BACKEND_MAIN.read_text(encoding="utf-8")
    health = source.split('@application.get("/health")', 1)[1].split(
        '@application.get("/api/dashboard")', 1
    )[0]
    dashboard = source.split('@application.get("/api/dashboard")', 1)[1]
    assert "engine.connect()" in health and 'text("SELECT 1")' in health
    assert "engine.connect()" in dashboard
    assert "SELECT name, value FROM dashboard_metrics ORDER BY display_order" in dashboard
    assert '"status": "operational"' in dashboard
    assert '"database": "reachable"' in dashboard


def test_dashboard_schema_and_seed_metrics_are_preserved():
    sql = (REPOSITORY / "database" / "init.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE dashboard_metrics" in sql
    assert "name TEXT PRIMARY KEY" in sql
    assert "value INTEGER NOT NULL" in sql
    assert "display_order INTEGER NOT NULL UNIQUE" in sql
    assert "('Jobs processed', 128, 1)" in sql
    assert "('Active workers', 4, 2)" in sql
    assert "('Pending alerts', 0, 3)" in sql


def test_frontend_consumes_dashboard_without_hard_coding():
    component = FRONTEND.read_text(encoding="utf-8")
    assert "${apiBaseUrl}/api/dashboard" in component
    assert "dashboard.status" in component
    assert "dashboard.database" in component
    assert "dashboard.metrics" in component
    for forbidden in ["Jobs processed", "Active workers", "Pending alerts", ">128<", ">4<"]:
        assert forbidden not in component
    assert "Dashboard unavailable." in component


def test_three_service_health_architecture_is_preserved():
    compose = COMPOSE.read_text(encoding="utf-8")
    assert len(re.findall(r"^  db:$", compose, re.MULTILINE)) == 1
    assert len(re.findall(r"^  backend:$", compose, re.MULTILINE)) == 1
    assert len(re.findall(r"^  frontend:$", compose, re.MULTILINE)) == 1
    assert compose.count("healthcheck:") == 3
    assert "postgres:16.6-alpine@sha256:1d04b9ba1d4996401f2552b51beda8187f175c0645c091e4781134fc9c9a3eef" in compose
    assert '"127.0.0.1:8000:8000"' in compose
    assert '"127.0.0.1:8080:80"' in compose
    assert "condition: service_healthy" in compose
    assert "condition: service_started" in compose
    source = BACKEND_MAIN.read_text(encoding="utf-8")
    assert 'FRONTEND_ORIGIN = "http://127.0.0.1:8080"' in source
    assert "allow_origins=[FRONTEND_ORIGIN]" in source
