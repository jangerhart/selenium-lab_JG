from __future__ import annotations

from pydantic import BaseModel, Field


class BookSection(BaseModel):
    """A logical text section extracted from the source PDF."""

    text: str = Field(min_length=1)
    source_page: int = Field(ge=1)


class ExtractionResult(BaseModel):
    """Clean text and diagnostics collected before translation."""

    sections: list[BookSection]
    page_count: int = Field(ge=1)
    character_count: int = Field(ge=1)
    estimated_tokens: int = Field(ge=1)
    removed_header_footer_lines: list[str]


class TranslationProgress(BaseModel):
    """Progress details emitted while translating chunks."""

    current: int
    total: int
    detail: str
