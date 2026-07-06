from __future__ import annotations

from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from blogbook.epub import write_epub
from blogbook.extract import extract_article
from blogbook.fetch import fetch_html
from blogbook.models import BookChapter, BookMetadata
from blogbook.translate import Translator

TARGET_LANGUAGE = "cs"


def create_book_from_file(
    urls_file: Path,
    output_path: Path,
    translator: Translator,
    title: Optional[str] = None,
) -> Path:
    urls = read_urls(urls_file)
    chapters = [_create_chapter(url, translator) for url in urls]
    metadata = _build_metadata(chapters, title)
    return write_epub(chapters, metadata, output_path)


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


def _create_chapter(url: str, translator: Translator) -> BookChapter:
    source_html = fetch_html(url)
    article = extract_article(source_html, url)
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
