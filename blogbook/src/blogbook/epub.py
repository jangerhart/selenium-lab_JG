from __future__ import annotations

from html import escape
from pathlib import Path
from uuid import uuid4

from ebooklib import epub

from blogbook.models import BookChapter, BookMetadata


def write_epub(chapters: list[BookChapter], metadata: BookMetadata, output_path: Path) -> Path:
    if not chapters:
        raise ValueError("Cannot write an EPUB without chapters.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    book = epub.EpubBook()
    book.set_identifier(str(uuid4()))
    book.set_title(metadata.title)
    book.set_language(metadata.language)
    if metadata.author:
        book.add_author(metadata.author)

    epub_chapters = []
    toc_links = []
    for index, source_chapter in enumerate(chapters, start=1):
        file_name = f"chapter-{index}.xhtml"
        chapter = epub.EpubHtml(
            title=source_chapter.title,
            file_name=file_name,
            lang=metadata.language,
        )
        source_link = (
            f"<p><small>Source: "
            f"<a href=\"{source_chapter.source_url}\">{source_chapter.source_url}</a>"
            f"</small></p>"
        )
        chapter.content = (
            f"<h1>{escape(source_chapter.title)}</h1>{source_link}{source_chapter.html}"
        )
        book.add_item(chapter)
        epub_chapters.append(chapter)
        toc_links.append(epub.Link(file_name, source_chapter.title, f"chapter-{index}"))

    book.toc = tuple(toc_links)
    book.spine = ["nav"] + epub_chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(str(output_path), book)
    return output_path
