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
