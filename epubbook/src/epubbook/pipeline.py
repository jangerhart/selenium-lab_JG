from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Optional, Protocol

from epubbook.epub import load_epub, write_translated_epub
from epubbook.models import EpubAnalysis, TextSegment
from epubbook.translate import ProgressCallback


class GenerationCancelled(RuntimeError):
    """Raised when the user declines after local EPUB analysis."""


class Translator(Protocol):
    def translate(
        self, segments: list[TextSegment], progress: Optional[ProgressCallback] = None
    ) -> dict[int, str]: ...


def translate_epub(
    input_path: Path,
    output_path: Path,
    translator: Translator,
    confirm: Optional[Callable[[EpubAnalysis], bool]] = None,
    progress: Optional[ProgressCallback] = None,
) -> Path:
    book = load_epub(input_path)
    if confirm is not None and not confirm(book.analysis):
        raise GenerationCancelled("Překlad byl zrušen. Vstupní EPUB zůstalo beze změny.")
    translations = translator.translate([slot.segment for slot in book.slots], progress)
    return write_translated_epub(book, translations, output_path)
