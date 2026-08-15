from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextSegment:
    """One replaceable text node in an EPUB XHTML document."""

    identifier: int
    document: str
    text: str


@dataclass(frozen=True)
class EpubAnalysis:
    """Local preflight information shown before any API request."""

    document_count: int
    segment_count: int
    character_count: int
    estimated_tokens: int

