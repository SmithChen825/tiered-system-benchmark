from pathlib import Path


def test_password_reset_api_smoke_contract_is_present():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    assert '"/health"' in source
    assert '"/api/v2/auth/password-reset"' in source
    assert 'status.HTTP_202_ACCEPTED' in source

