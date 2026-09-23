from pathlib import Path

def test_customer_api_and_database_contract_are_present():
    root=Path(__file__).resolve().parents[2]
    assert '"/api/customers"' in (root/"backend"/"app"/"main.py").read_text(encoding="utf-8")
    assert "status TEXT NOT NULL" in (root/"database"/"init.sql").read_text(encoding="utf-8")
