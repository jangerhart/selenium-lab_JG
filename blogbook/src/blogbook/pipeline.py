from __future__ import annotations

from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from blogbook.epub import write_epub
from blogbook.extract import extract_article
from blogbook.fetch import fetch_html
from blogbook.models import BookMetadata
from blogbook.translate import Translator


def create_book_from_url(
    url: str,
    output_path: Path,
    translator: Translator,
    target_language: str = "cs",
    title: Optional[str] = None,
    author: Optional[str] = None,
) -> Path:
    source_html = fetch_html(url)
    article = extract_article(source_html, url)
    translated_html = translator.translate_html(article.html, target_language)
    translated_title = title or article.title

    metadata = BookMetadata(
        title=translated_title,
        author=author or article.author or "Unknown author",
        language=target_language,
        source_url=article.source_url,
    )
    return write_epub(_ensure_body_fragment(translated_html), metadata, output_path)


def _ensure_body_fragment(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body
    if body:
        return "".join(str(child) for child in body.children).strip()
    return html.strip()
