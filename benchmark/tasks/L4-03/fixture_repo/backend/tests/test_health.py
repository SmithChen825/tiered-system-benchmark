from pathlib import Path


def test_database_backed_health_contract_is_present():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    assert '"/health"' in source
    assert '"/api/dashboard"' in source
    assert 'connection.execute(text("SELECT 1"))' in source

