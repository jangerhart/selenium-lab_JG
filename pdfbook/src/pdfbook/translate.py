from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

from openai import OpenAI, OpenAIError

from pdfbook.models import BookSection

TARGET_LANGUAGE = "Czech"
MAX_CHUNK_CHARACTERS = 12_000
ProgressCallback = Callable[[int, int, str], None]


class TranslationError(RuntimeError):
    """Raised when translation cannot be completed."""


@dataclass(frozen=True)
class OpenAITranslator:
    model: str = "gpt-4.1-mini"

    def translate_sections(
        self,
        sections: list[BookSection],
        progress: Optional[ProgressCallback] = None,
    ) -> list[str]:
        chunks = make_chunks(sections)
        translated = []
        for index, chunk in enumerate(chunks, start=1):
            if progress:
                progress(index, len(chunks), f"blok {index}")
            translated.append(self._translate_chunk(chunk))
        return translated

    def _translate_chunk(self, text: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
        if not api_key:
            raise TranslationError(
                "Chybí OPENAI_API_KEY nebo API_KEY. "
                "Použijte stejnou proměnnou prostředí jako u Blogbooku."
            )
        try:
            response = OpenAI(api_key=api_key).responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "Translate the supplied book text into natural Czech. "
                            "Preserve paragraph boundaries and the marker [[PARAGRAPH]]. "
                            "Do not summarize, omit, explain, or add content. Preserve copyright "
                            "notices, headings, quotations, footnotes, and lists. Return only the "
                            "translated text."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Target language: {TARGET_LANGUAGE}\n\n{text}",
                    },
                ],
            )
        except OpenAIError as exc:
            raise TranslationError(f"Překlad selhal: {exc}") from exc

        output = response.output_text.strip()
        if not output:
            raise TranslationError("Překlad vrátil prázdný výsledek.")
        return output


def make_chunks(sections: list[BookSection]) -> list[str]:
    chunks = []
    current: list[str] = []
    current_length = 0
    separator = "\n\n[[PARAGRAPH]]\n\n"

    for section in sections:
        parts = _split_long_text(section.text, MAX_CHUNK_CHARACTERS)
        for part in parts:
            added_length = len(part) + (len(separator) if current else 0)
            if current and current_length + added_length > MAX_CHUNK_CHARACTERS:
                chunks.append(separator.join(current))
                current = []
                current_length = 0
            current.append(part)
            current_length += len(part) + (len(separator) if len(current) > 1 else 0)

    if current:
        chunks.append(separator.join(current))
    return chunks


def translated_paragraphs(chunks: list[str]) -> list[str]:
    paragraphs = []
    for chunk in chunks:
        for value in chunk.split("[[PARAGRAPH]]"):
            cleaned = value.strip()
            if cleaned:
                paragraphs.append(cleaned)
    return paragraphs


def _split_long_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts = []
    remaining = text
    while len(remaining) > limit:
        boundary = remaining.rfind(" ", 0, limit)
        if boundary < limit // 2:
            boundary = limit
        parts.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()
    if remaining:
        parts.append(remaining)
    return parts
