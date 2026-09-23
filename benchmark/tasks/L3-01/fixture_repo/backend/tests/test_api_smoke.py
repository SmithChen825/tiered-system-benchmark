from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint():
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_account_endpoint_returns_contract_directly():
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
