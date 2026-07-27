from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from pypdf import PdfReader

from pdfbook.models import BookSection, ExtractionResult

MIN_TEXT_CHARACTERS = 200
EDGE_LINE_COUNT = 3


class PdfExtractionError(RuntimeError):
    """Raised when a PDF does not contain enough machine-readable text."""


def extract_pdf(input_path: Path) -> ExtractionResult:
    try:
        reader = PdfReader(str(input_path))
    except (OSError, ValueError) as exc:
        raise PdfExtractionError(f"PDF nelze otevřít: {exc}") from exc

    if reader.is_encrypted:
        try:
            unlocked = reader.decrypt("")
        except Exception as exc:
            raise PdfExtractionError("PDF je zašifrované a nelze jej přečíst.") from exc
        if not unlocked:
            raise PdfExtractionError("PDF je chráněné heslem.")

    raw_pages = [(page.extract_text() or "") for page in reader.pages]
    if not raw_pages:
        raise PdfExtractionError("PDF neobsahuje žádné stránky.")

    repeated_edges = find_repeated_edge_lines(raw_pages)
    sections = []
    for page_number, raw_text in enumerate(raw_pages, start=1):
        cleaned = clean_page_text(raw_text, repeated_edges)
        for paragraph in split_paragraphs(cleaned):
            sections.append(BookSection(text=paragraph, source_page=page_number))

    character_count = sum(len(section.text) for section in sections)
    if character_count < MIN_TEXT_CHARACTERS:
        raise PdfExtractionError(
            "PDF neobsahuje dostatek strojově čitelného textu. "
            "Skenované nebo obrazové PDF není podporováno."
        )

    return ExtractionResult(
        sections=sections,
        page_count=len(raw_pages),
        character_count=character_count,
        estimated_tokens=estimate_translation_tokens(
            "\n\n".join(section.text for section in sections)
        ),
        removed_header_footer_lines=sorted(repeated_edges),
    )


def find_repeated_edge_lines(pages: list[str]) -> set[str]:
    if len(pages) < 2:
        return set()

    counter: Counter[str] = Counter()
    display_values: dict[str, str] = {}
    for page in pages:
        lines = _meaningful_lines(page)
        candidates = lines[:EDGE_LINE_COUNT] + lines[-EDGE_LINE_COUNT:]
        seen_on_page = set()
        for line in candidates:
            normalized = normalize_repeated_line(line)
            if not normalized or normalized in seen_on_page or _is_page_number(line):
                continue
            seen_on_page.add(normalized)
            counter[normalized] += 1
            display_values.setdefault(normalized, line.strip())

    threshold = max(2, math.ceil(len(pages) * 0.5))
    return {
        display_values[normalized]
        for normalized, count in counter.items()
        if count >= threshold
    }


def clean_page_text(text: str, repeated_edges: set[str]) -> str:
    lines = [line.strip() for line in text.splitlines()]
    repeated_normalized = {normalize_repeated_line(line) for line in repeated_edges}
    kept = []
    for line in lines:
        if _is_page_number(line):
            continue
        if normalize_repeated_line(line) in repeated_normalized:
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def split_paragraphs(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n", text)
    paragraphs = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        joined = _join_wrapped_lines(lines)
        if joined:
            paragraphs.append(joined)
    return paragraphs


def estimate_translation_tokens(text: str) -> int:
    input_tokens = math.ceil(len(text) / 4) + 150
    output_tokens = math.ceil(input_tokens * 1.15)
    return input_tokens + output_tokens


def normalize_repeated_line(line: str) -> str:
    value = re.sub(r"\d+", "#", line.casefold())
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t-|")


def _join_wrapped_lines(lines: Iterable[str]) -> str:
    result = ""
    for line in lines:
        if not result:
            result = line
        elif result.endswith("-") and line[:1].islower():
            result = result[:-1] + line
        else:
            result += " " + line
    return re.sub(r"\s+", " ", result).strip()


def _meaningful_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_page_number(line: str) -> bool:
    value = line.strip()
    return bool(
        re.fullmatch(r"(?:page\s+)?\d+(?:\s+(?:of|/)\s+\d+)?", value, flags=re.IGNORECASE)
        or re.fullmatch(r"[ivxlcdm]+", value, flags=re.IGNORECASE)
        or re.fullmatch(r"[-–—]\s*\d+\s*[-–—]", value)
    )
