from html.parser import HTMLParser
import os
from pathlib import Path


REPOSITORY = Path(os.environ["L1_03_REPO"]).resolve()
INDEX = REPOSITORY / "site" / "index.html"
SCRIPT = REPOSITORY / "site" / "assets" / "contact-form.js"


class ContactParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_form = False
        self.form_attributes = {}
        self.fields = []
        self.labels = []
        self.button = {}
        self.status = {}
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form" and values.get("id") == "contact-form":
            self.in_form = True
            self.form_attributes = values
        elif self.in_form and tag in {"input", "textarea"}:
            self.fields.append((tag, values))
        elif self.in_form and tag == "label":
            self.labels.append(values.get("for"))
        elif self.in_form and tag == "button":
            self.button = values
        elif self.in_form and tag == "p" and values.get("id") == "form-status":
            self.status = values
        elif tag == "script":
            self.scripts.append(values)

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_form = False


def parsed_page():
    parser = ContactParser()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    return parser


def test_contact_form_contract_is_preserved():
    parser = parsed_page()
    assert "novalidate" in parser.form_attributes
    assert [field[1].get("id") for field in parser.fields] == [
        "contact-name",
        "contact-email",
        "contact-message",
    ]
    assert [field[1].get("name") for field in parser.fields] == [
        "name",
        "email",
        "message",
    ]
    assert parser.labels == ["contact-name", "contact-email", "contact-message"]
    assert parser.button.get("type") == "submit"
    assert parser.status.get("role") == "status"
    assert parser.status.get("aria-live") == "polite"


def test_contact_form_loads_existing_validation_script():
    parser = parsed_page()
    assert parser.scripts == [{"src": "/assets/contact-form.js", "defer": None}]
    assert SCRIPT.is_file()


def test_supplied_bundle_preserves_validation_and_success_contract():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'form.addEventListener("submit"' in source
    assert "event.preventDefault()" in source
    assert 'data.get("name")' in source
    assert 'data.get("email")' in source
    assert 'data.get("message")' in source
    assert "Please complete every field with a valid email address." in source
    assert "Your message is ready to send." in source
    assert 'show(`Thanks, ${name}.' in source
    assert "form.reset()" in source


def test_repair_does_not_replace_the_existing_validation_architecture():
    parser = parsed_page()
    html = INDEX.read_text(encoding="utf-8").lower()
    assert len(parser.scripts) == 1
    assert parser.scripts[0].get("src", "").startswith("/assets/")
    assert not parser.scripts[0].get("src", "").startswith(("http://", "https://", "//"))
    assert "action" not in parser.form_attributes
    assert "required" not in html
    assert "onsubmit" not in html


def test_nginx_exact_path_404_policy_is_preserved():
    nginx = (REPOSITORY / "nginx.conf").read_text(encoding="utf-8")
    assert "try_files $uri $uri/ =404;" in nginx

