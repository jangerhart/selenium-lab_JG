from pathlib import Path

import pytest

import blogbook.pipeline as pipeline
from blogbook.extract import ExtractionError
from blogbook.models import Article, PreflightSummary
from blogbook.translate import TranslationError


def _article(url: str, title: str = "Post") -> Article:
    text = " ".join(["useful"] * 50)
    return Article(
        source_url=url,
        title=title,
        html=f"<article><p>{text}</p></article>",
        text=text,
    )


def test_preflight_skips_bad_urls_and_estimates_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch(url: str) -> str:
        if url.endswith("/offline"):
            raise pipeline.FetchError("offline")
        return "<html></html>"

    def fake_extract(_: str, url: str) -> Article:
        if url.endswith("/empty"):
            raise ExtractionError("not an article")
        return _article(url)

    monkeypatch.setattr(pipeline, "fetch_html", fake_fetch)
    monkeypatch.setattr(pipeline, "extract_article", fake_extract)

    articles, summary = pipeline.preflight_urls(
        [
            "https://example.com/good",
            "https://example.com/offline",
            "https://example.com/empty",
        ]
    )

    assert len(articles) == 1
    assert summary.usable_urls == 1
    assert summary.skipped_urls == 2
    assert summary.estimated_tokens > 0


def test_create_book_asks_before_translation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    article = _article("https://example.com/post")
    summary = PreflightSummary(
        total_urls=1,
        usable_urls=1,
        skipped_urls=0,
        estimated_tokens=500,
        items=[],
    )
    translated = False

    class Translator:
        def translate_html(self, html: str, target_language: str) -> str:
            nonlocal translated
            translated = True
            return html

    monkeypatch.setattr(
        pipeline,
        "preflight_urls",
        lambda urls, progress=None: ([article], summary),
    )
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text("https://example.com/post\n")

    with pytest.raises(pipeline.GenerationCancelled):
        pipeline.create_book_from_file(
            urls_file,
            tmp_path / "book.epub",
            Translator(),
            confirm=lambda _: False,
        )

    assert translated is False


def test_translation_failure_is_skipped_and_next_article_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    articles = [
        _article("https://example.com/one", "One"),
        _article("https://example.com/two", "Two"),
    ]
    summary = PreflightSummary(
        total_urls=2,
        usable_urls=2,
        skipped_urls=0,
        estimated_tokens=1000,
        items=[],
    )

    class Translator:
        calls = 0

        def translate_html(self, html: str, target_language: str) -> str:
            self.calls += 1
            if self.calls == 1:
                raise TranslationError("temporary failure")
            return html

    written: list[str] = []
    monkeypatch.setattr(pipeline, "preflight_urls", lambda urls, progress=None: (articles, summary))
    monkeypatch.setattr(
        pipeline,
        "write_epub",
        lambda chapters, metadata, output: written.extend(c.title for c in chapters) or output,
    )
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text("https://example.com/one\nhttps://example.com/two\n")

    pipeline.create_book_from_file(
        urls_file,
        tmp_path / "book.epub",
        Translator(),
        confirm=lambda _: True,
    )

    assert written == ["Two"]
