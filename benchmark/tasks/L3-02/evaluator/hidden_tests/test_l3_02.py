import os, sys
from pathlib import Path
from fastapi.testclient import TestClient

REPOSITORY = Path(os.environ["L3_02_REPO"]).resolve(); BACKEND = REPOSITORY / "backend"
if str(BACKEND) not in sys.path: sys.path.insert(0, str(BACKEND))
from app.main import ORDER, create_app  # noqa: E402

def test_backend_order_contract_uses_renamed_field():
    with TestClient(create_app()) as client: response = client.get("/api/orders/ORD-2048")
    assert response.status_code == 200
    assert response.json() == {"id":"ORD-2048","customer":"Maya Chen","order_status":"Ready for dispatch","updated_at":"2026-08-28T09:30:00Z"}

def test_frontend_consumes_the_current_order_status_field():
    component = (REPOSITORY / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
    assert "order.order_status" in component and "order.status" not in component

def test_order_status_is_not_hard_coded_in_frontend():
    component = (REPOSITORY / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
    assert ORDER["order_status"] not in component and "fetch(" in component

def test_frontend_targets_the_frozen_order_endpoint():
    component = (REPOSITORY / "frontend" / "src" / "App.vue").read_text(encoding="utf-8")
    assert "${apiBaseUrl}/api/orders/ORD-2048" in component

def test_services_and_cors_boundary_remain_preserved():
    compose = (REPOSITORY / "compose.yaml").read_text(encoding="utf-8")
    assert "  backend:" in compose and "  frontend:" in compose
    with TestClient(create_app()) as client:
        response = client.get("/api/orders/ORD-2048", headers={"Origin":"http://127.0.0.1:8080"})
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:8080"
