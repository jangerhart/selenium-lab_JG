from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI


class Translator(Protocol):
    def translate_html(self, html: str, target_language: str) -> str:
        """Translate article HTML while preserving basic markup."""


@dataclass(frozen=True)
class NoopTranslator:
    def translate_html(self, html: str, target_language: str) -> str:
        return html


@dataclass(frozen=True)
class OpenAITranslator:
    model: str = "gpt-4.1-mini"

    def translate_html(self, html: str, target_language: str) -> str:
        client = OpenAI()
        response = client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Translate the user's HTML article into the requested language. "
                        "Preserve semantic HTML tags, links, headings, lists, and code blocks. "
                        "Return only translated HTML."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Target language: {target_language}\n\nHTML:\n{html}",
                },
            ],
        )
        return response.output_text.strip()

