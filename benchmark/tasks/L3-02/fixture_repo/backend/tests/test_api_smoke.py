from pathlib import Path

def test_order_api_smoke_contract_is_present():
    source=(Path(__file__).resolve().parents[1]/"app"/"main.py").read_text(encoding="utf-8")
    assert '"/health"' in source
    assert '"/api/orders/{order_id}"' in source
    assert '"order_status": "Ready for dispatch"' in source
