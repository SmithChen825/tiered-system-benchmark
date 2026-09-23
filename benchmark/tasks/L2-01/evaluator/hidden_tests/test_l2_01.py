import os, sys
from pathlib import Path
from fastapi.testclient import TestClient

REPOSITORY = Path(os.environ["L2_01_REPO"]).resolve()
if str(REPOSITORY) not in sys.path: sys.path.insert(0, str(REPOSITORY))
from app.main import ITEMS, create_app  # noqa: E402

def test_item_detail_route_returns_expected_item():
    with TestClient(create_app()) as client: response = client.get("/items/2")
    assert response.status_code == 200
    assert "Harbor Pack" in response.text and "Carry" in response.text and "$129.00" in response.text

def test_each_index_link_resolves_to_its_detail_page():
    with TestClient(create_app()) as client:
        index = client.get("/"); assert index.status_code == 200
        for item_id, item in ITEMS.items():
            assert f'href="/items/{item_id}"' in index.text
            detail = client.get(f"/items/{item_id}")
            assert detail.status_code == 200 and item["name"] in detail.text

def test_json_item_contract_remains_available():
    with TestClient(create_app()) as client: response = client.get("/api/items/1")
    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "Aurora Lamp", "category": "Lighting", "price": 79.0}

def test_unknown_item_returns_404_not_a_fallback_item():
    with TestClient(create_app()) as client: response = client.get("/items/999")
    assert response.status_code == 404

def test_route_uses_the_declared_path_parameter_without_query_fallback():
    source = (REPOSITORY / "app" / "main.py").read_text(encoding="utf-8")
    assert '"/items/{item_id}"' in source
    assert "def item_detail(item_id: int)" in source
    assert "product_id" not in source

def test_service_health_and_single_service_architecture_are_preserved():
    with TestClient(create_app()) as client: assert client.get("/health").json() == {"status": "ok"}
    compose = (REPOSITORY / "compose.yaml").read_text(encoding="utf-8")
    assert compose.count("services:") == 1 and "  app:" in compose
