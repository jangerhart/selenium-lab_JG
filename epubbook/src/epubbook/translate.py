from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI, OpenAIError

from epubbook.models import TextSegment

MAX_CHUNK_CHARACTERS = 12_000
ProgressCallback = Callable[[int, int, str], None]


class TranslationError(RuntimeError):
    """Raised when translation cannot be completed without losing content."""


@dataclass(frozen=True)
class OpenAITranslator:
    model: str = "gpt-4.1-mini"

    def translate(
        self, segments: list[TextSegment], progress: Optional[ProgressCallback] = None
    ) -> dict[int, str]:
        chunks = make_chunks(segments)
        result: dict[int, str] = {}
        for index, chunk in enumerate(chunks, start=1):
            if progress:
                progress(index, len(chunks), f"blok {index}")
            result.update(self._translate_chunk(chunk))
        return result

    def _translate_chunk(self, segments: list[TextSegment]) -> dict[int, str]:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
        if not api_key:
            raise TranslationError("Chybí OPENAI_API_KEY nebo API_KEY.")
        payload = [{"id": item.identifier, "text": item.text.strip()} for item in segments]
        try:
            response = OpenAI(api_key=api_key).responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "Translate every JSON item's text into natural Czech. Keep every id, "
                            "do not omit, merge, summarize or add content. Text items may be "
                            "fragments separated by inline XHTML formatting, so preserve their "
                            "role. Return only a JSON array with objects containing the same "
                            "integer id and translated text."
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            )
        except OpenAIError as exc:
            raise TranslationError(f"Překlad selhal: {exc}") from exc
        try:
            data = json.loads(response.output_text)
            translated = {int(item["id"]): str(item["text"]) for item in data}
        except (ValueError, TypeError, KeyError) as exc:
            raise TranslationError("Model nevrátil platný seznam překladů.") from exc
        expected = {item.identifier for item in segments}
        if set(translated) != expected or any(not value.strip() for value in translated.values()):
            raise TranslationError("Model vynechal nebo přidal textovou část; EPUB nebyl vytvořen.")
        return translated


def make_chunks(segments: list[TextSegment]) -> list[list[TextSegment]]:
    chunks: list[list[TextSegment]] = []
    current: list[TextSegment] = []
    current_size = 0
    for segment in segments:
        size = len(segment.text) + 30
        if current and current_size + size > MAX_CHUNK_CHARACTERS:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(segment)
        current_size += size
    if current:
        chunks.append(current)
    return chunks
