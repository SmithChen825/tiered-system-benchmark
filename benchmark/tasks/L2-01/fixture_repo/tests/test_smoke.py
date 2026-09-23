import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.main import create_app

def test_health_and_item_api_smoke():
    with TestClient(create_app()) as client:
        assert client.get("/health").json()=={"status":"ok"}
        assert client.get("/api/items/2").json()["name"]=="Harbor Pack"
