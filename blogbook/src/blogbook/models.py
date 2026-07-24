from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class Article(BaseModel):
    """Clean article content extracted from a web page."""

    source_url: HttpUrl
    title: str = Field(min_length=1)
    author: Optional[str] = None
    language: Optional[str] = None
    html: str = Field(min_length=1)
    text: str = Field(min_length=1)


class BookMetadata(BaseModel):
    """Metadata used when writing the EPUB."""

    title: str = Field(min_length=1)
    author: Optional[str] = None
    language: str = "cs"
    source_url: Optional[HttpUrl] = None


class BookChapter(BaseModel):
    """One EPUB chapter derived from one source blog post."""

    title: str = Field(min_length=1)
    html: str = Field(min_length=1)
    source_url: HttpUrl
    author: Optional[str] = None


class PreflightItem(BaseModel):
    """Result of checking one URL before any translation is attempted."""

    url: str
    usable: bool
    title: Optional[str] = None
    characters: int = 0
    estimated_tokens: int = 0
    reason: Optional[str] = None


class PreflightSummary(BaseModel):
    """Summary shown to the user before token-consuming work starts."""

    total_urls: int
    usable_urls: int
    skipped_urls: int
    estimated_tokens: int
    items: list[PreflightItem]
