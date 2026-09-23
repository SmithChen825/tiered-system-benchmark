from pathlib import Path


def test_contact_form_and_external_bundle_are_supplied():
    root = Path(__file__).resolve().parents[1]
    html = (root / "site" / "index.html").read_text(encoding="utf-8")
    script = root / "site" / "assets" / "contact-form.js"
    assert 'id="contact-form"' in html
    assert 'id="contact-name"' in html
    assert 'id="contact-email"' in html
    assert 'id="contact-message"' in html
    assert 'id="form-status"' in html
    assert script.is_file()

