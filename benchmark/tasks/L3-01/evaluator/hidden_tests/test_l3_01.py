import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


REPOSITORY = Path(os.environ["L3_01_REPO"]).resolve()
BACKEND = REPOSITORY / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import ALLOWED_ORIGINS, create_app  # noqa: E402


EXPECTED_ORIGIN = "http://127.0.0.1:8080"
STALE_ORIGIN = "http://127.0.0.1:5173"


def test_direct_account_endpoint_remains_healthy():
    with TestClient(create_app()) as client:
        response = client.get("/api/account")

    assert response.status_code == 200
    assert response.json() == {
        "id": 1042,
        "name": "Ada Lovelace",
        "role": "Platform Engineer",
        "plan": "Research",
        "active": True,
    }


def test_expected_origin_receives_cors_header_on_get():
    with TestClient(create_app()) as client:
        response = client.get("/api/account", headers={"Origin": EXPECTED_ORIGIN})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == EXPECTED_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_expected_origin_preflight_is_accepted():
    with TestClient(create_app()) as client:
        response = client.options(
            "/api/account",
            headers={
                "Origin": EXPECTED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == EXPECTED_ORIGIN
    assert "GET" in response.headers.get("access-control-allow-methods", "")


def test_backend_policy_names_the_frozen_frontend_origin():
    assert ALLOWED_ORIGINS == [EXPECTED_ORIGIN]
    assert "*" not in ALLOWED_ORIGINS


def test_stale_development_origin_is_not_allowed():
    with TestClient(create_app()) as client:
        response = client.get("/api/account", headers={"Origin": STALE_ORIGIN})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_unrelated_origin_is_not_allowed():
    with TestClient(create_app()) as client:
        response = client.get(
            "/api/account", headers={"Origin": "https://unrelated.example"}
        )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_frontend_keeps_frozen_backend_address_without_proxy_or_fallback():
    component = (REPOSITORY / "frontend" / "src" / "App.vue").read_text(
        encoding="utf-8"
    )
    compose = (REPOSITORY / "compose.yaml").read_text(encoding="utf-8")
    vite_config = (REPOSITORY / "frontend" / "vite.config.js").read_text(
        encoding="utf-8"
    )

    assert "http://127.0.0.1:8000" in component
    assert 'VITE_API_BASE_URL: "http://127.0.0.1:8000"' in compose
    assert "proxy" not in vite_config.lower()
    assert 'name: "Ada Lovelace"' not in component


def test_frontend_and_backend_remain_separate_services():
    compose = (REPOSITORY / "compose.yaml").read_text(encoding="utf-8")
    assert "services:" in compose
    assert "  backend:" in compose
    assert "  frontend:" in compose
    assert "context: ./backend" in compose
    assert "context: ./frontend" in compose
    assert '"127.0.0.1:8000:8000"' in compose
    assert '"127.0.0.1:8080:80"' in compose
