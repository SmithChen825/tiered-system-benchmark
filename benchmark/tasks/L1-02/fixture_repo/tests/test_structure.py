from pathlib import Path

def test_navigation_and_mobile_viewport_are_present():
    root=Path(__file__).resolve().parents[1]; html=(root/"site"/"index.html").read_text(encoding="utf-8"); css=(root/"site"/"assets"/"styles.css").read_text(encoding="utf-8")
    assert 'class="site-nav"' in html and html.count('href="#') >= 4
    assert "@media (max-width: 640px)" in css
