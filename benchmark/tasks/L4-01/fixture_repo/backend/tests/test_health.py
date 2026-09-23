from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint_does_not_require_database_query():
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_frontend_origin_policy_remains_named():
    with TestClient(create_app()) as client:
        response = client.get(
            "/health", headers={"Origin": "http://127.0.0.1:8080"}
        )

    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:8080"
