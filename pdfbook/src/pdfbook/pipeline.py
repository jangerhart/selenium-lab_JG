from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from pdfbook.extract import extract_pdf
from pdfbook.models import ExtractionResult
from pdfbook.render import write_pdf
from pdfbook.translate import OpenAITranslator, ProgressCallback, translated_paragraphs


class GenerationCancelled(RuntimeError):
    """Raised when the user declines after seeing the preflight summary."""


def translate_pdf(
    input_path: Path,
    output_path: Path,
    translator: OpenAITranslator,
    title: Optional[str] = None,
    confirm: Optional[Callable[[ExtractionResult], bool]] = None,
    progress: Optional[ProgressCallback] = None,
) -> Path:
    result = extract_pdf(input_path)
    if confirm is not None and not confirm(result):
        raise GenerationCancelled("Překlad byl zrušen. Vstupní PDF zůstalo beze změny.")
    chunks = translator.translate_sections(result.sections, progress)
    return write_pdf(translated_paragraphs(chunks), output_path, title)
