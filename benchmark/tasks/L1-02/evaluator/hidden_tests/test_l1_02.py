from html.parser import HTMLParser
import os
from pathlib import Path

REPOSITORY = Path(os.environ["L1_02_REPO"]).resolve()
INDEX = REPOSITORY / "site" / "index.html"
STYLES = REPOSITORY / "site" / "assets" / "styles.css"

class NavigationParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.in_nav = False; self.nav_label = ""; self.links = []
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "nav" and "site-nav" in values.get("class", ""):
            self.in_nav = True; self.nav_label = values.get("aria-label", "")
        elif self.in_nav and tag == "a": self.links.append(values.get("href", ""))
    def handle_endtag(self, tag):
        if tag == "nav": self.in_nav = False

def test_primary_navigation_identity_and_targets_are_preserved():
    parser = NavigationParser(); parser.feed(INDEX.read_text(encoding="utf-8"))
    assert parser.nav_label == "Primary navigation"
    assert parser.links == ["#home", "#guides", "#equipment", "#contact"]

def test_mobile_media_query_targets_the_current_navigation_dom():
    css = STYLES.read_text(encoding="utf-8")
    mobile = css.split("@media (max-width: 640px)", 1)[1]
    assert ".site-nav" in mobile and ".nav-links" not in mobile
    assert "flex-direction: column" in mobile and "white-space: normal" in mobile

def test_mobile_fix_does_not_hide_navigation_or_replace_it_with_script():
    combined = INDEX.read_text(encoding="utf-8") + STYLES.read_text(encoding="utf-8")
    assert "display: none" not in combined and "<script" not in combined.lower()

def test_desktop_navigation_layout_remains_horizontal():
    before_media = STYLES.read_text(encoding="utf-8").split("@media", 1)[0]
    assert ".site-nav" in before_media and "display: flex" in before_media
    assert "justify-content: flex-end" in before_media

def test_nginx_exact_path_404_policy_is_preserved():
    assert "try_files $uri $uri/ =404;" in (REPOSITORY / "nginx.conf").read_text(encoding="utf-8")
