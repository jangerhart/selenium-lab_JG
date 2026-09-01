from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

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


@dataclass(frozen=True)
class VariantMatch:
    scope: str
    matched_suffix: str | None = None


def normalize_variant_token(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^0-9A-Za-z]+", "", value).upper()


def _read_shared_strings(zip_file: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zip_file.namelist():
        return []
    root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for si in root.findall("a:si", NS):
        values.append("".join(t.text or "" for t in si.findall(".//a:t", NS)))
    return values


def split_suffix_cell(value: str) -> list[str]:
    parts = []
    for token in re.split(r"[;,]", value):
        cleaned = token.strip().lower()
        if cleaned:
            parts.append(cleaned)
    return parts


def load_alternative_suffixes(workbook_path: Path) -> list[str]:
    with ZipFile(workbook_path) as zip_file:
        shared_strings = _read_shared_strings(zip_file)
        workbook = ET.fromstring(zip_file.read("xl/workbook.xml"))
        rels = ET.fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}

        raw_values: list[str] = []
        for sheet in workbook.find("a:sheets", NS):
            target = "xl/" + rel_map[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
            root = ET.fromstring(zip_file.read(target))

            for row in root.findall(".//a:sheetData/a:row", NS):
                if row.attrib.get("r") == "1":
                    continue
                for cell in row.findall("a:c", NS):
                    if not cell.attrib.get("r", "").startswith("A"):
                        continue
                    cell_type = cell.attrib.get("t")
                    raw_value = cell.findtext("a:v", default="", namespaces=NS)
                    if cell_type == "s":
                        raw_values.append(shared_strings[int(raw_value)])
                    elif cell_type == "inlineStr":
                        raw_values.append("".join(t.text or "" for t in cell.findall(".//a:t", NS)))
                    elif raw_value:
                        raw_values.append(raw_value)

    suffixes: list[str] = []
    for value in raw_values:
        for token in split_suffix_cell(value):
            if token not in suffixes:
                suffixes.append(token)
    suffixes.sort(key=len, reverse=True)
    return suffixes


VARIANT_SUFFIX_CATALOG_DDL = [
    "CREATE SCHEMA IF NOT EXISTS reporting",
    """
    CREATE TABLE IF NOT EXISTS reporting.variant_suffix_catalog (
        suffix text PRIMARY KEY,
        enabled boolean NOT NULL DEFAULT true,
        source text NOT NULL DEFAULT 'excel',
        note text,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE OR REPLACE VIEW reporting.variant_suffix_catalog_v AS
    SELECT
        suffix,
        enabled,
        source,
        note,
        length(suffix) AS suffix_length,
        created_at,
        updated_at
    FROM reporting.variant_suffix_catalog
    WHERE enabled = true
    ORDER BY length(suffix) DESC, suffix ASC
    """,
]


def seed_variant_suffix_catalog(conn, workbook_path: Path) -> int:
    suffixes = load_alternative_suffixes(workbook_path)
    inserted = 0
    with conn.cursor() as cur:
        for suffix in suffixes:
            cur.execute(
                """
                INSERT INTO reporting.variant_suffix_catalog (suffix, enabled, source, note)
                VALUES (%s, true, 'excel', 'seeded from rozliseni_alternativ.xlsx')
                ON CONFLICT (suffix) DO NOTHING
                """,
                (suffix,),
            )
            inserted += cur.rowcount or 0
    return inserted


def fetch_variant_suffixes(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT suffix
            FROM reporting.variant_suffix_catalog_v
            ORDER BY suffix_length DESC, suffix ASC
            """
        )
        return [str(row[0]) for row in cur.fetchall()]


def load_known_identifiers(workbook_rows: list[str]) -> set[str]:
    return {normalize_variant_token(value) for value in workbook_rows if value}


def classify_sandix_variant(identifier: str | None, known_identifiers: set[str], suffixes: list[str]) -> VariantMatch:
    normalized = normalize_variant_token(identifier)
    for suffix in suffixes:
        if normalized.endswith(suffix):
            base = normalized[: -len(suffix)]
            if base and base in known_identifiers:
                return VariantMatch("ALTERNATIVE", suffix)
    return VariantMatch("ORIGINAL")


def classify_competitor_variant(
    identifier: str | None,
    product_name: str | None,
    product_url: str | None,
    suffixes: list[str],
) -> VariantMatch:
    normalized_identifier = normalize_variant_token(identifier)
    normalized_text = normalize_variant_token(" ".join([identifier or "", product_name or "", product_url or ""]))

    for suffix in suffixes:
        if len(suffix) >= 2 and normalized_identifier.endswith(suffix):
            return VariantMatch("ALTERNATIVE", suffix)
        if len(suffix) >= 3 and suffix in normalized_text:
            return VariantMatch("ALTERNATIVE", suffix)

    for hint in ALT_HINTS:
        if normalize_variant_token(hint) in normalized_text:
            return VariantMatch("ALTERNATIVE", hint)

    return VariantMatch("ORIGINAL")


VARIANT_ANALYTICS_DDL = [
    "CREATE SCHEMA IF NOT EXISTS reporting",
    """
    CREATE TABLE IF NOT EXISTS reporting.profibagr_variant_batch_kpi (
        source_run_id uuid NOT NULL,
        comparison_scope text NOT NULL,
        competitor_code text NOT NULL,
        competitor_name text NOT NULL,
        generated_at timestamptz NOT NULL,
        batch_started_at timestamptz NOT NULL,
        batch_finished_at timestamptz,
        request_count integer NOT NULL,
        search_success_count integer NOT NULL,
        not_found_count integer NOT NULL,
        error_count integer NOT NULL,
        raw_offer_count integer NOT NULL,
        valid_offer_count integer NOT NULL,
        invalid_offer_count integer NOT NULL,
        mismatch_offer_count integer NOT NULL,
        matched_product_count integer NOT NULL,
        sandix_more_expensive_count integer NOT NULL,
        sandix_cheaper_count integer NOT NULL,
        equal_price_count integer NOT NULL,
        average_gap_pct_vs_competitor numeric(10,2),
        max_positive_gap_pct_vs_competitor numeric(10,2),
        max_negative_gap_pct_vs_competitor numeric(10,2),
        PRIMARY KEY (source_run_id, comparison_scope)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reporting.profibagr_variant_price_comparison (
        source_run_id uuid NOT NULL,
        comparison_scope text NOT NULL,
        product_id bigint NOT NULL,
        source_identifier text,
        searched_identifier text NOT NULL,
        product_name text,
        sandix_price_net numeric(18,4),
        sandix_price_gross numeric(18,4),
        profibagr_price_net numeric(18,4),
        profibagr_price_gross numeric(18,4),
        profibagr_product_url text,
        price_gap_net numeric(18,4),
        price_gap_gross numeric(18,4),
        price_gap_pct_vs_competitor numeric(10,2),
        raw_offer_count integer NOT NULL,
        valid_offer_count integer NOT NULL,
        invalid_offer_count integer NOT NULL,
        search_request_count integer NOT NULL,
        generated_at timestamptz NOT NULL,
        PRIMARY KEY (source_run_id, comparison_scope, product_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reporting.profibagr_variant_search_status (
        source_run_id uuid NOT NULL,
        comparison_scope text NOT NULL,
        search_status text NOT NULL,
        request_count integer NOT NULL,
        request_pct numeric(10,2) NOT NULL,
        generated_at timestamptz NOT NULL,
        PRIMARY KEY (source_run_id, comparison_scope, search_status)
    )
    """,
    """
    CREATE OR REPLACE VIEW reporting.profibagr_latest_batch_original_v AS
    SELECT *
    FROM reporting.profibagr_variant_batch_kpi
    WHERE comparison_scope = 'ORIGINAL'
      AND source_run_id = (
          SELECT source_run_id
          FROM reporting.profibagr_variant_batch_kpi
          WHERE comparison_scope = 'ORIGINAL'
          ORDER BY generated_at DESC, batch_finished_at DESC NULLS LAST
          LIMIT 1
      )
    """,
    """
    CREATE OR REPLACE VIEW reporting.profibagr_latest_batch_alternative_v AS
    SELECT *
    FROM reporting.profibagr_variant_batch_kpi
    WHERE comparison_scope = 'ALTERNATIVE'
      AND source_run_id = (
          SELECT source_run_id
          FROM reporting.profibagr_variant_batch_kpi
          WHERE comparison_scope = 'ALTERNATIVE'
          ORDER BY generated_at DESC, batch_finished_at DESC NULLS LAST
          LIMIT 1
      )
    """,
    """
    CREATE OR REPLACE VIEW reporting.profibagr_latest_price_comparison_original_v AS
    SELECT *
    FROM reporting.profibagr_variant_price_comparison
    WHERE comparison_scope = 'ORIGINAL'
      AND source_run_id = (
          SELECT source_run_id
          FROM reporting.profibagr_variant_batch_kpi
          WHERE comparison_scope = 'ORIGINAL'
          ORDER BY generated_at DESC, batch_finished_at DESC NULLS LAST
          LIMIT 1
      )
    ORDER BY price_gap_pct_vs_competitor DESC NULLS LAST, price_gap_gross DESC NULLS LAST, product_name
    """,
    """
    CREATE OR REPLACE VIEW reporting.profibagr_latest_price_comparison_alternative_v AS
    SELECT *
    FROM reporting.profibagr_variant_price_comparison
    WHERE comparison_scope = 'ALTERNATIVE'
      AND source_run_id = (
          SELECT source_run_id
          FROM reporting.profibagr_variant_batch_kpi
          WHERE comparison_scope = 'ALTERNATIVE'
          ORDER BY generated_at DESC, batch_finished_at DESC NULLS LAST
          LIMIT 1
      )
    ORDER BY price_gap_pct_vs_competitor DESC NULLS LAST, price_gap_gross DESC NULLS LAST, product_name
    """,
    """
    CREATE OR REPLACE VIEW reporting.profibagr_latest_search_status_original_v AS
    SELECT *
    FROM reporting.profibagr_variant_search_status
    WHERE comparison_scope = 'ORIGINAL'
      AND source_run_id = (
          SELECT source_run_id
          FROM reporting.profibagr_variant_batch_kpi
          WHERE comparison_scope = 'ORIGINAL'
          ORDER BY generated_at DESC, batch_finished_at DESC NULLS LAST
          LIMIT 1
      )
    ORDER BY CASE search_status WHEN 'OK' THEN 1 WHEN 'NOT_FOUND' THEN 2 ELSE 3 END
    """,
    """
    CREATE OR REPLACE VIEW reporting.profibagr_latest_search_status_alternative_v AS
    SELECT *
    FROM reporting.profibagr_variant_search_status
    WHERE comparison_scope = 'ALTERNATIVE'
      AND source_run_id = (
          SELECT source_run_id
          FROM reporting.profibagr_variant_batch_kpi
          WHERE comparison_scope = 'ALTERNATIVE'
          ORDER BY generated_at DESC, batch_finished_at DESC NULLS LAST
          LIMIT 1
      )
    ORDER BY CASE search_status WHEN 'OK' THEN 1 WHEN 'NOT_FOUND' THEN 2 ELSE 3 END
    """,
]
