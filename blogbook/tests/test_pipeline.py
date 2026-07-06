from pathlib import Path

from blogbook.pipeline import _ensure_body_fragment
from blogbook.translate import NoopTranslator


def test_noop_translator_returns_html_unchanged() -> None:
    html = "<p>Hello</p>"

    assert NoopTranslator().translate_html(html, "cs") == html


def test_ensure_body_fragment_extracts_body_children() -> None:
    html = "<html><body><p>Hello</p></body></html>"

    assert _ensure_body_fragment(html) == "<p>Hello</p>"


def test_path_import_keeps_public_api_typable() -> None:
    assert Path("book.epub").suffix == ".epub"

