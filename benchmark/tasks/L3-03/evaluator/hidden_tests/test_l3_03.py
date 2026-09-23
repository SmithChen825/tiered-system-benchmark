import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient


REPOSITORY = Path(os.environ["L3_03_REPO"]).resolve()
BACKEND = REPOSITORY / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import FRONTEND_ORIGIN, create_app  # noqa: E402


def test_backend_current_password_reset_contract():
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v2/auth/password-reset",
            json={"email": " Maya@Example.Test "},
        )
    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "email": "maya@example.test",
        "request_id": "RST-2048",
    }


def test_retired_password_reset_route_remains_404():
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/auth/password-reset",
            json={"email": "maya@example.test"},
        )
    assert response.status_code == 404


def test_frontend_targets_the_current_password_reset_endpoint():
    component = (REPOSITORY / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
    assert "${apiBaseUrl}/api/v2/auth/password-reset" in component
    assert "/api/v1/auth/password-reset" not in component


def test_frontend_form_and_response_contract_are_preserved():
    component = (REPOSITORY / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
    assert 'data-testid="reset-form"' in component
    assert 'data-testid="reset-email"' in component
    assert 'data-testid="reset-submit"' in component
    assert 'method: "POST"' in component
    assert '"Content-Type": "application/json"' in component
    assert "JSON.stringify({ email: email.value })" in component
    assert "result.email" in component
    assert "Unable to submit password reset." in component


def test_frontend_does_not_proxy_or_hard_code_success():
    component = (REPOSITORY / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
    vite = (REPOSITORY / "frontend" / "vite.config.js").read_text(encoding="utf-8")
    nginx = (REPOSITORY / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert "import.meta.env.VITE_API_BASE_URL" in component
    assert "maya@example.test" not in component.lower()
    assert "proxy" not in vite.lower()
    assert "proxy_pass" not in nginx.lower()


def test_services_ports_and_cors_boundary_remain_preserved():
    compose = (REPOSITORY / "compose.yaml").read_text(encoding="utf-8")
    assert "  backend:" in compose and "  frontend:" in compose
    assert '"127.0.0.1:8000:8000"' in compose
    assert '"127.0.0.1:8080:80"' in compose
    assert 'VITE_API_BASE_URL: "http://127.0.0.1:8000"' in compose
    with TestClient(create_app()) as client:
        preflight = client.options(
            "/api/v2/auth/password-reset",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        trusted = client.post(
            "/api/v2/auth/password-reset",
            json={"email": "maya@example.test"},
            headers={"Origin": FRONTEND_ORIGIN},
        )
        untrusted = client.post(
            "/api/v2/auth/password-reset",
            json={"email": "maya@example.test"},
            headers={"Origin": "http://127.0.0.1:5173"},
        )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN
    assert "POST" in preflight.headers.get("access-control-allow-methods", "")
    assert trusted.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN
    assert "access-control-allow-origin" not in untrusted.headers

