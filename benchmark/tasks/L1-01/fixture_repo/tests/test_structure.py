from html.parser import HTMLParser
from pathlib import Path


SITE_ROOT = Path(__file__).resolve().parents[1] / "site"


class ProductParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.product_ids: list[str] = []
        self.image_alts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "article" and "product-card" in (attributes.get("class") or ""):
            product_id = attributes.get("data-product-id")
            if product_id:
                self.product_ids.append(product_id)
        if tag == "img":
            alt = attributes.get("alt")
            if alt:
                self.image_alts.append(alt)


def test_catalogue_keeps_three_accessible_product_cards():
    parser = ProductParser()
    parser.feed((SITE_ROOT / "index.html").read_text(encoding="utf-8"))

    assert parser.product_ids == ["aurora-lamp", "harbor-pack", "mesa-mug"]
    assert len(parser.image_alts) == 3
    assert all(parser.image_alts)


def test_stylesheet_is_present():
    assert (SITE_ROOT / "assets" / "styles.css").is_file()
