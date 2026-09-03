from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from sandix.alternatives import normalize_variant_token


ALT_HINTS = (
    "OEM",
    "NAHRADA",
    "NÁHRADA",
    "ALTERNATIV",
    "ALTERNATIVE",
    "REPLACEMENT",
    "PRVOVYROBA",
    "BASICLINE",
    "PREMIUMLINE",
)

TOKEN_SPLIT_RE = re.compile(r"[\s;,|]+")


@dataclass(frozen=True)
class IdentifierClassification:
    raw_identifier: str
    normalized_identifier: str
    normalized_base_identifier: str
    matched_suffixes: tuple[str, ...]
    variant_scope: str
    classification_reason: str


def split_identifier_tokens(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [token for token in TOKEN_SPLIT_RE.split(raw_value.strip()) if token]


def normalize_part_number_token(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^0-9A-Za-z/]+", "", value).upper()


def strip_variant_suffixes(value: str | None, suffixes: Sequence[str]) -> tuple[str, tuple[str, ...]]:
    raw_value = (value or "").strip()
    matched_suffixes: list[str] = []
    ordered_suffixes = sorted([suffix.strip() for suffix in suffixes if suffix], key=len, reverse=True)

    while raw_value:
        matched = None
        raw_lower = raw_value.lower()
        for suffix in ordered_suffixes:
            if raw_lower.endswith(suffix.lower()):
                matched = suffix
                break
        if not matched:
            break
        raw_value = raw_value[: -len(matched)].rstrip()
        matched_suffixes.append(matched)

    return normalize_part_number_token(raw_value), tuple(matched_suffixes)


def dedupe_part_numbers_by_base(values: Sequence[str], suffixes: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        base_identifier, _ = strip_variant_suffixes(value, suffixes)
        if base_identifier and base_identifier not in seen:
            seen.add(base_identifier)
            deduped.append(base_identifier)
    return deduped


def classify_source_identifier(raw_identifier: str, suffixes: Sequence[str]) -> IdentifierClassification:
    normalized_identifier = normalize_part_number_token(raw_identifier)
    normalized_base_identifier, matched_suffixes = strip_variant_suffixes(raw_identifier, suffixes)
    return IdentifierClassification(
        raw_identifier=raw_identifier,
        normalized_identifier=normalized_identifier,
        normalized_base_identifier=normalized_base_identifier,
        matched_suffixes=matched_suffixes,
        variant_scope="ALTERNATIVE" if matched_suffixes else "ORIGINAL",
        classification_reason="SUFFIX_STRIPPED" if matched_suffixes else "NO_SUFFIX",
    )


def classify_competitor_search_identifier(raw_identifier: str, suffixes: Sequence[str]) -> IdentifierClassification:
    classification = classify_source_identifier(raw_identifier, suffixes)
    reason = "SEARCH_INPUT_SUFFIX" if classification.matched_suffixes else "SEARCH_INPUT_ORIGINAL"
    return IdentifierClassification(
        raw_identifier=classification.raw_identifier,
        normalized_identifier=classification.normalized_identifier,
        normalized_base_identifier=classification.normalized_base_identifier,
        matched_suffixes=classification.matched_suffixes,
        variant_scope=classification.variant_scope,
        classification_reason=reason,
    )


def classify_competitor_observation(
    searched_identifier: str | None,
    found_identifier: str | None,
    competitor_product_name: str | None,
    product_url: str | None,
    suffixes: Sequence[str],
) -> IdentifierClassification:
    raw_source = found_identifier or competitor_product_name or product_url or ""
    normalized_identifier = normalize_part_number_token(raw_source)
    normalized_base_identifier, matched_suffixes = strip_variant_suffixes(raw_source, suffixes)

    searchable_text = normalize_variant_token(" ".join([found_identifier or "", competitor_product_name or "", product_url or ""]))
    hint = next((value for value in ALT_HINTS if normalize_variant_token(value) in searchable_text), None)

    searched_base_identifier = strip_variant_suffixes(searched_identifier, suffixes)[0] if searched_identifier else ""
    if matched_suffixes:
        scope = "ALTERNATIVE"
        reason = "IDENTIFIER_SUFFIX"
    elif hint:
        scope = "ALTERNATIVE"
        reason = "TEXT_HINT"
    elif searched_base_identifier and normalized_base_identifier and normalized_base_identifier == searched_base_identifier:
        scope = "ORIGINAL"
        reason = "BASE_MATCH"
    else:
        scope = "UNRESOLVED"
        reason = "NO_ALT_MARKER"

    return IdentifierClassification(
        raw_identifier=raw_source,
        normalized_identifier=normalized_identifier,
        normalized_base_identifier=normalized_base_identifier,
        matched_suffixes=matched_suffixes,
        variant_scope=scope,
        classification_reason=reason,
    )


FILTER_REVIEW_DDL = [
    "CREATE SCHEMA IF NOT EXISTS reporting",
    """
    CREATE TABLE IF NOT EXISTS reporting.part_number_filter_review (
        filter_review_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        source_domain text NOT NULL,
        row_kind text NOT NULL,
        source_sync_run_id uuid,
        scrape_run_id uuid,
        product_id bigint,
        pohoda_id bigint,
        search_request_id bigint,
        observation_id bigint,
        source_database text,
        product_name text,
        search_identifier text,
        search_identifier_normalized text,
        raw_part_number text NOT NULL,
        normalized_part_number text NOT NULL,
        normalized_base_part_number text NOT NULL,
        matched_suffixes text,
        variant_scope text NOT NULL,
        classification_reason text NOT NULL,
        competitor_product_name text,
        product_url text,
        match_type text,
        match_confidence numeric(5,4),
        row_ordinal integer NOT NULL,
        generated_at timestamptz NOT NULL
    )
    """,
    """
    CREATE OR REPLACE VIEW reporting.part_number_filter_latest_v AS
    SELECT *
    FROM reporting.part_number_filter_review
    WHERE generated_at = (
        SELECT MAX(generated_at)
        FROM reporting.part_number_filter_review
    )
    ORDER BY source_domain, row_kind, variant_scope, normalized_base_part_number, raw_part_number
    """,
    """
    CREATE OR REPLACE VIEW reporting.part_number_filter_latest_summary_v AS
    SELECT
        source_domain,
        row_kind,
        variant_scope,
        classification_reason,
        COUNT(*)::int AS row_count
    FROM reporting.part_number_filter_latest_v
    GROUP BY 1, 2, 3, 4
    ORDER BY source_domain, row_kind, variant_scope, classification_reason
    """,
]
