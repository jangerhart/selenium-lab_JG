from __future__ import annotations

from html import escape
from pathlib import Path
from uuid import uuid4

from ebooklib import epub

from blogbook.models import BookMetadata


def write_epub(html: str, metadata: BookMetadata, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    book = epub.EpubBook()
    book.set_identifier(str(uuid4()))
    book.set_title(metadata.title)
    book.set_language(metadata.language)
    book.add_author(metadata.author)

    chapter = epub.EpubHtml(
        title=metadata.title,
        file_name="chapter-1.xhtml",
        lang=metadata.language,
    )
    source_link = (
        f"<p><small>Source: <a href=\"{metadata.source_url}\">{metadata.source_url}</a></small></p>"
        if metadata.source_url
        else ""
    )
    chapter.content = f"<h1>{escape(metadata.title)}</h1>{source_link}{html}"

    book.add_item(chapter)
    book.toc = (epub.Link("chapter-1.xhtml", metadata.title, "chapter-1"),)
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(str(output_path), book)
    return output_path
