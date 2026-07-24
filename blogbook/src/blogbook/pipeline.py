from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Optional

from bs4 import BeautifulSoup

from blogbook.epub import write_epub
from blogbook.extract import ExtractionError, extract_article
from blogbook.fetch import FetchError, fetch_html
from blogbook.models import (
    Article,
    BookChapter,
    BookMetadata,
    PreflightItem,
    PreflightSummary,
)
from blogbook.translate import TranslationError, Translator

TARGET_LANGUAGE = "cs"
MIN_ARTICLE_WORDS = 40
ProgressCallback = Callable[[str, int, int, str], None]


class NoUsableArticlesError(ValueError):
    """Raised when no checked URL can produce a book chapter."""


class GenerationCancelled(RuntimeError):
    """Raised when the user declines generation after preflight."""


def create_book_from_file(
    urls_file: Path,
    output_path: Path,
    translator: Translator,
    title: Optional[str] = None,
    confirm: Optional[Callable[[PreflightSummary], bool]] = None,
    progress: Optional[ProgressCallback] = None,
) -> Path:
    urls = read_urls(urls_file)
    articles, summary = preflight_urls(urls, progress=progress)
    if confirm is not None and not confirm(summary):
        raise GenerationCancelled(
            "Generation cancelled. You can edit the URL file and run the command again."
        )

    chapters = []
    total = len(articles)
    for index, article in enumerate(articles, start=1):
        _report(progress, "translate", index, total, article.title)
        try:
            chapters.append(_create_chapter(article, translator))
        except TranslationError as exc:
            _report(progress, "skip", index, total, f"{article.source_url}: {exc}")

    if not chapters:
        raise NoUsableArticlesError("No chapters were generated.")

    metadata = _build_metadata(chapters, title)
    return write_epub(chapters, metadata, output_path)


def preflight_urls(
    urls: list[str],
    progress: Optional[ProgressCallback] = None,
) -> tuple[list[Article], PreflightSummary]:
    """Fetch and validate every URL without making translation API calls."""
    articles = []
    items = []
    total = len(urls)

    for index, url in enumerate(urls, start=1):
        _report(progress, "check", index, total, url)
        try:
            article = extract_article(fetch_html(url), url)
            word_count = len(article.text.split())
            if word_count < MIN_ARTICLE_WORDS:
                raise ExtractionError(
                    f"Extracted content is too short ({word_count} words; "
                    f"minimum is {MIN_ARTICLE_WORDS})."
                )
        except (FetchError, ExtractionError, ValueError) as exc:
            items.append(PreflightItem(url=url, usable=False, reason=str(exc)))
            _report(progress, "skip", index, total, f"{url}: {exc}")
            continue
        except Exception as exc:
            # Parser failures are page-specific and must not abort a large batch.
            reason = f"Could not process page: {exc}"
            items.append(PreflightItem(url=url, usable=False, reason=reason))
            _report(progress, "skip", index, total, f"{url}: {reason}")
            continue

        token_estimate = estimate_translation_tokens(article.html)
        articles.append(article)
        items.append(
            PreflightItem(
                url=url,
                usable=True,
                title=article.title,
                characters=len(article.text),
                estimated_tokens=token_estimate,
            )
        )

    summary = PreflightSummary(
        total_urls=total,
        usable_urls=len(articles),
        skipped_urls=total - len(articles),
        estimated_tokens=sum(item.estimated_tokens for item in items),
        items=items,
    )
    if not articles:
        reasons = "; ".join(item.reason or item.url for item in items)
        raise NoUsableArticlesError(f"No usable blog articles found. {reasons}")
    return articles, summary


def estimate_translation_tokens(html: str) -> int:
    """Conservative input + output estimate; actual usage depends on the model/language."""
    prompt_overhead = 120
    input_tokens = math.ceil(len(html) / 4) + prompt_overhead
    estimated_output_tokens = math.ceil(input_tokens * 1.1)
    return input_tokens + estimated_output_tokens


def read_urls(urls_file: Path) -> list[str]:
    urls = []
    for line in urls_file.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        urls.append(value)

    if not urls:
        raise ValueError(f"No URLs found in {urls_file}.")

    return urls


def _create_chapter(article: Article, translator: Translator) -> BookChapter:
    translated_html = translator.translate_html(article.html, TARGET_LANGUAGE)

    return BookChapter.model_validate(
        {
            "title": article.title,
            "html": _ensure_body_fragment(translated_html),
            "source_url": article.source_url,
            "author": article.author,
        }
    )


def _build_metadata(chapters: list[BookChapter], title: Optional[str]) -> BookMetadata:
    book_author = _single_author(chapters)
    book_title = title or (chapters[0].title if len(chapters) == 1 else "Blogbook")

    return BookMetadata(
        title=book_title,
        author=book_author,
        language=TARGET_LANGUAGE,
        source_url=chapters[0].source_url if len(chapters) == 1 else None,
    )


def _single_author(chapters: list[BookChapter]) -> Optional[str]:
    authors = {chapter.author for chapter in chapters if chapter.author}
    if len(authors) == 1:
        return authors.pop()
    return None


def _ensure_body_fragment(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body
    if body:
        return "".join(str(child) for child in body.children).strip()
    return html.strip()


def _report(
    progress: Optional[ProgressCallback],
    phase: str,
    current: int,
    total: int,
    detail: str,
) -> None:
    if progress is not None:
        progress(phase, current, total, detail)
