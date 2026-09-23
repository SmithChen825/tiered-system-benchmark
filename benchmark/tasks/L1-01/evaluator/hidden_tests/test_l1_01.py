from html.parser import HTMLParser
import os
from pathlib import Path
from urllib.parse import urlparse


REPOSITORY = Path(os.environ["L1_01_REPO"]).resolve()
SITE_ROOT = REPOSITORY / "site"
INDEX = SITE_ROOT / "index.html"


class CatalogueParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, str]] = []
        self.product_ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "img":
            self.images.append(attributes)
        if tag == "article" and "product-card" in attributes.get("class", ""):
            self.product_ids.append(attributes.get("data-product-id", ""))


def parsed_catalogue() -> CatalogueParser:
    parser = CatalogueParser()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    return parser


def test_all_product_image_paths_resolve_to_repository_files():
    images = parsed_catalogue().images
    assert len(images) == 3

    resolved_assets = []
    for image in images:
        source = image["src"]
        path = (SITE_ROOT / source.lstrip("/")).resolve()
        assert path.is_relative_to(SITE_ROOT.resolve())
        assert path.is_file(), f"Missing repository asset for {source}"
        assert path.stat().st_size > 0
        resolved_assets.append(path)

    assert len(set(resolved_assets)) == 3


def test_retired_asset_directory_is_not_referenced():
    assert "/legacy-assets/" not in INDEX.read_text(encoding="utf-8")


def test_product_images_remain_local_and_not_embedded():
    for image in parsed_catalogue().images:
        source = image["src"]
        parsed = urlparse(source)
        assert parsed.scheme == ""
        assert parsed.netloc == ""
        assert not source.startswith("data:")


def test_catalogue_identity_and_accessible_text_are_preserved():
    parser = parsed_catalogue()
    assert parser.product_ids == ["aurora-lamp", "harbor-pack", "mesa-mug"]
    assert [image.get("alt") for image in parser.images] == [
        "Aurora camp lamp",
        "Harbor day pack",
        "Mesa trail mug",
    ]
    html = INDEX.read_text(encoding="utf-8")
    assert "Aurora Camp Lamp" in html
    assert "Harbor Day Pack" in html
    assert "Mesa Trail Mug" in html


def test_supplied_product_assets_are_not_duplicated_or_renamed():
    product_directory = SITE_ROOT / "assets" / "products"
    assert sorted(path.name for path in product_directory.glob("*.svg")) == [
        "aurora-lamp.svg",
        "harbor-pack.svg",
        "mesa-mug.svg",
    ]


def test_nginx_keeps_missing_resource_failures_visible():
    configuration = (REPOSITORY / "nginx.conf").read_text(encoding="utf-8")
    assert "try_files $uri $uri/ =404;" in configuration
    assert "legacy-assets" not in configuration
