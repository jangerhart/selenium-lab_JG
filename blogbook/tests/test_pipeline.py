from pathlib import Path

import pytest
from openai import OpenAIError

import blogbook.translate as translate_module
from blogbook.models import BookChapter
from blogbook.pipeline import _build_metadata, _ensure_body_fragment, read_urls
from blogbook.translate import NoopTranslator, OpenAITranslator


def test_noop_translator_returns_html_unchanged() -> None:
    html = "<p>Hello</p>"

    assert NoopTranslator().translate_html(html, "cs") == html


def test_openai_translator_uses_api_key_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        output_text = "<p>Přeloženo</p>"

    class FakeOpenAI:
        def __init__(self, api_key: object = None) -> None:
            captured["api_key"] = api_key

        @property
        def responses(self) -> object:
            return self

        def create(self, **_: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(translate_module, "OpenAI", FakeOpenAI)

    assert OpenAITranslator().translate_html("<p>Hello</p>", "cs") == "<p>Přeloženo</p>"
    assert captured["api_key"] == "test-key"


def test_openai_translator_surfaces_openai_error_details(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOpenAI:
        def __init__(self, api_key: object = None) -> None:
            pass

        @property
        def responses(self) -> object:
            return self

        def create(self, **_: object) -> object:
            raise OpenAIError("Error code: 429 - insufficient_quota")

    monkeypatch.setattr(translate_module, "OpenAI", FakeOpenAI)

    with pytest.raises(translate_module.TranslationError, match="insufficient_quota"):
        OpenAITranslator().translate_html("<p>Hello</p>", "cs")


def test_ensure_body_fragment_extracts_body_children() -> None:
    html = "<html><body><p>Hello</p></body></html>"

    assert _ensure_body_fragment(html) == "<p>Hello</p>"


def test_path_import_keeps_public_api_typable() -> None:
    assert Path("book.epub").suffix == ".epub"


def test_read_urls_ignores_blank_lines_and_comments(tmp_path: Path) -> None:
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text(
        "\n# reading list\nhttps://example.com/one\n  https://example.com/two  \n",
        encoding="utf-8",
    )

    assert read_urls(urls_file) == ["https://example.com/one", "https://example.com/two"]


def test_read_urls_requires_at_least_one_url(tmp_path: Path) -> None:
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text("# empty\n", encoding="utf-8")

    with pytest.raises(ValueError, match="No URLs found"):
        read_urls(urls_file)


def test_build_metadata_uses_single_chapter_title_and_author() -> None:
    chapter = BookChapter.model_validate(
        {
            "title": "Header Title",
            "html": "<p>Text</p>",
            "source_url": "https://example.com/post",
            "author": "Ada Lovelace",
        }
    )

    metadata = _build_metadata([chapter], title=None)

    assert metadata.title == "Header Title"
    assert metadata.author == "Ada Lovelace"
    assert metadata.language == "cs"


def test_build_metadata_omits_mixed_authors_for_multi_chapter_book() -> None:
    chapters = [
        BookChapter.model_validate(
            {
                "title": "One",
                "html": "<p>Text</p>",
                "source_url": "https://example.com/one",
                "author": "Ada Lovelace",
            }
        ),
        BookChapter.model_validate(
            {
                "title": "Two",
                "html": "<p>Text</p>",
                "source_url": "https://example.com/two",
                "author": "Grace Hopper",
            }
        ),
    ]

    metadata = _build_metadata(chapters, title="Collected Posts")

    assert metadata.title == "Collected Posts"
    assert metadata.author is None
