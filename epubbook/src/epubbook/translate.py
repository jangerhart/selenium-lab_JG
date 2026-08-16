from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI, OpenAIError

from epubbook.models import TextSegment

MAX_CHUNK_CHARACTERS = 8_000
SINGLE_SEGMENT_ATTEMPTS = 3
ProgressCallback = Callable[[int, int, str], None]


class TranslationError(RuntimeError):
    """Raised when translation cannot be completed without losing content."""


class ResponseValidationError(TranslationError):
    """Raised when a model response does not match the requested text segments."""


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
            result.update(self._translate_resilient(chunk, progress))
        return result

    def _translate_resilient(
        self,
        segments: list[TextSegment],
        progress: Optional[ProgressCallback] = None,
    ) -> dict[int, str]:
        attempts = SINGLE_SEGMENT_ATTEMPTS if len(segments) == 1 else 1
        last_error: Optional[ResponseValidationError] = None
        for attempt in range(1, attempts + 1):
            try:
                return self._translate_chunk(segments)
            except ResponseValidationError as exc:
                last_error = exc
                if progress and attempts > 1 and attempt < attempts:
                    progress(0, 0, f"opakování textové části {segments[0].identifier}")

        if len(segments) > 1:
            midpoint = len(segments) // 2
            if progress:
                progress(0, 0, f"dělení problematického bloku ({len(segments)} částí)")
            left = self._translate_resilient(segments[:midpoint], progress)
            right = self._translate_resilient(segments[midpoint:], progress)
            return {**left, **right}

        identifier = segments[0].identifier
        raise TranslationError(
            f"Model ani po {attempts} pokusech nepřeložil textovou část {identifier}."
        ) from last_error

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
            data = json.loads(_strip_json_fence(response.output_text))
            translated = {int(item["id"]): str(item["text"]) for item in data}
        except (ValueError, TypeError, KeyError) as exc:
            raise ResponseValidationError("Model nevrátil platný seznam překladů.") from exc
        expected = {item.identifier for item in segments}
        if set(translated) != expected or any(not value.strip() for value in translated.values()):
            raise ResponseValidationError("Model vynechal nebo přidal textovou část.")
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


def _strip_json_fence(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return cleaned
