from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sandix.part_numbers import (  # noqa: E402
    FILTER_REVIEW_DDL,
    classify_competitor_observation,
    classify_competitor_search_identifier,
    classify_source_identifier,
    split_identifier_tokens,
)
from sandix.alternatives import (  # noqa: E402
    VARIANT_SUFFIX_CATALOG_DDL,
    fetch_variant_suffixes,
    seed_variant_suffix_catalog,
)


def get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_env_default(name: str, default: str) -> str:
    return os.getenv(name) or default


def connect(dbname: str, prefix: str) -> psycopg.Connection:
    conn_kwargs: dict[str, object] = {
        "host": os.getenv(f"{prefix}_HOST") or get_env("PG_PROVISION_HOST"),
        "port": int(os.getenv(f"{prefix}_PORT") or get_env("PG_PROVISION_PORT")),
        "dbname": dbname,
        "user": os.getenv(f"{prefix}_USER") or get_env("PG_PROVISION_USER"),
        "password": os.getenv(f"{prefix}_PASSWORD") or get_env("PG_PROVISION_PASSWORD"),
    }
    sslmode = os.getenv(f"{prefix}_SSLMODE") or os.getenv("PG_PROVISION_SSLMODE")
    if sslmode:
        conn_kwargs["sslmode"] = sslmode
    return psycopg.connect(**conn_kwargs)


def ensure_reporting_objects(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        for statement in FILTER_REVIEW_DDL + VARIANT_SUFFIX_CATALOG_DDL:
            cur.execute(statement)


def fetch_source_rows(conn: psycopg.Connection) -> list[dict[str, object]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                p.product_id,
                p.pohoda_id,
                p.source_database,
                s.ids,
                s.product_name,
                s.last_sync_run_id
            FROM core.product p
            JOIN source_pohoda.stock_current s
              ON s.source_database = p.source_database
             AND s.pohoda_id = p.pohoda_id
            WHERE s.ids IS NOT NULL
              AND btrim(s.ids) <> ''
            ORDER BY p.product_id
            """
        )
        columns = [desc.name for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def fetch_latest_successful_scrape_run(conn: psycopg.Connection) -> dict[str, object]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, competitor_code, competitor_name, started_at, finished_at
            FROM export.scrape_run_v
            WHERE status = 'SUCCESS'
            ORDER BY started_at DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("No successful Profibagr scrape run found")
        columns = [desc.name for desc in cur.description]
    return dict(zip(columns, row))


def fetch_request_product_rows(conn: psycopg.Connection, scrape_run_id: uuid.UUID) -> list[dict[str, object]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT
                sr.search_request_id,
                sr.searched_identifier,
                sr.status,
                sp.product_id,
                sp.source_identifier,
                cp.source_database,
                cp.pohoda_id,
                cp.product_name
            FROM scraper.search_request sr
            JOIN scraper.search_request_product sp
              ON sp.search_request_id = sr.search_request_id
            JOIN core.product_current_v cp
              ON cp.product_id = sp.product_id
            WHERE sr.run_id = %s
            ORDER BY sr.search_request_id, sp.product_id
            """,
            (scrape_run_id,),
        )
        columns = [desc.name for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def fetch_observation_rows(conn: psycopg.Connection, scrape_run_id: uuid.UUID) -> list[dict[str, object]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                sr.search_request_id,
                sr.searched_identifier,
                sr.status,
                sp.product_id,
                sp.source_identifier,
                cp.source_database,
                cp.pohoda_id,
                cp.product_name,
                oo.observation_id,
                oo.found_identifier,
                oo.competitor_product_name,
                oo.product_url,
                oo.match_type,
                oo.match_confidence
            FROM scraper.search_request sr
            JOIN scraper.search_request_product sp
              ON sp.search_request_id = sr.search_request_id
            JOIN core.product_current_v cp
              ON cp.product_id = sp.product_id
            JOIN scraper.offer_observation oo
              ON oo.search_request_id = sr.search_request_id
            WHERE sr.run_id = %s
            ORDER BY sr.search_request_id, oo.observation_id, sp.product_id
            """,
            (scrape_run_id,),
        )
        columns = [desc.name for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def build_source_rows(rows: list[dict[str, object]], suffixes: list[str], generated_at: datetime) -> list[dict[str, object]]:
    review_rows: list[dict[str, object]] = []
    for row in rows:
        tokens = split_identifier_tokens(row["ids"])
        for ordinal, token in enumerate(tokens, start=1):
            classification = classify_source_identifier(token, suffixes)
            review_rows.append(
                {
                    "source_domain": "SANDIX",
                    "row_kind": "SOURCE_TOKEN",
                    "source_sync_run_id": row["last_sync_run_id"],
                    "scrape_run_id": None,
                    "product_id": row["product_id"],
                    "pohoda_id": row["pohoda_id"],
                    "search_request_id": None,
                    "observation_id": None,
                    "source_database": row["source_database"],
                    "product_name": row["product_name"],
                    "search_identifier": None,
                    "search_identifier_normalized": None,
                    "raw_part_number": classification.raw_identifier,
                    "normalized_part_number": classification.normalized_identifier,
                    "normalized_base_part_number": classification.normalized_base_identifier,
                    "matched_suffixes": ";".join(classification.matched_suffixes) or None,
                    "variant_scope": classification.variant_scope,
                    "classification_reason": classification.classification_reason,
                    "competitor_product_name": None,
                    "product_url": None,
                    "match_type": None,
                    "match_confidence": None,
                    "row_ordinal": ordinal,
                    "generated_at": generated_at,
                }
            )
    return review_rows


def build_request_rows(rows: list[dict[str, object]], suffixes: list[str], scrape_run_id: uuid.UUID, generated_at: datetime) -> list[dict[str, object]]:
    review_rows: list[dict[str, object]] = []
    for ordinal, row in enumerate(rows, start=1):
        classification = classify_competitor_search_identifier(row["searched_identifier"], suffixes)
        review_rows.append(
            {
                "source_domain": "PROFIBAGR",
                "row_kind": "SEARCH_REQUEST",
                "source_sync_run_id": None,
                "scrape_run_id": scrape_run_id,
                "product_id": row["product_id"],
                "pohoda_id": row["pohoda_id"],
                "search_request_id": row["search_request_id"],
                "observation_id": None,
                "source_database": row["source_database"],
                "product_name": row["product_name"],
                "search_identifier": row["searched_identifier"],
                "search_identifier_normalized": classification.normalized_identifier,
                "raw_part_number": classification.raw_identifier,
                "normalized_part_number": classification.normalized_identifier,
                "normalized_base_part_number": classification.normalized_base_identifier,
                "matched_suffixes": ";".join(classification.matched_suffixes) or None,
                "variant_scope": classification.variant_scope,
                "classification_reason": classification.classification_reason,
                "competitor_product_name": None,
                "product_url": None,
                "match_type": None,
                "match_confidence": None,
                "row_ordinal": ordinal,
                "generated_at": generated_at,
            }
        )
    return review_rows


def build_observation_rows(rows: list[dict[str, object]], suffixes: list[str], scrape_run_id: uuid.UUID, generated_at: datetime) -> list[dict[str, object]]:
    review_rows: list[dict[str, object]] = []
    for ordinal, row in enumerate(rows, start=1):
        classification = classify_competitor_observation(
            row["searched_identifier"],
            row["found_identifier"],
            row["competitor_product_name"],
            row["product_url"],
            suffixes,
        )
        review_rows.append(
            {
                "source_domain": "PROFIBAGR",
                "row_kind": "OFFER_OBSERVATION",
                "source_sync_run_id": None,
                "scrape_run_id": scrape_run_id,
                "product_id": row["product_id"],
                "pohoda_id": row["pohoda_id"],
                "search_request_id": row["search_request_id"],
                "observation_id": row["observation_id"],
                "source_database": row["source_database"],
                "product_name": row["product_name"],
                "search_identifier": row["searched_identifier"],
                "search_identifier_normalized": None,
                "raw_part_number": classification.raw_identifier,
                "normalized_part_number": classification.normalized_identifier,
                "normalized_base_part_number": classification.normalized_base_identifier,
                "matched_suffixes": ";".join(classification.matched_suffixes) or None,
                "variant_scope": classification.variant_scope,
                "classification_reason": classification.classification_reason,
                "competitor_product_name": row["competitor_product_name"],
                "product_url": row["product_url"],
                "match_type": row["match_type"],
                "match_confidence": row["match_confidence"],
                "row_ordinal": ordinal,
                "generated_at": generated_at,
            }
        )
    return review_rows


def write_snapshot(conn: psycopg.Connection, rows: list[dict[str, object]], source_sync_run_id: uuid.UUID | None, scrape_run_id: uuid.UUID | None) -> None:
    with conn.cursor() as cur:
        if source_sync_run_id is not None:
            cur.execute("DELETE FROM reporting.part_number_filter_review WHERE source_sync_run_id = %s", (source_sync_run_id,))
        if scrape_run_id is not None:
            cur.execute("DELETE FROM reporting.part_number_filter_review WHERE scrape_run_id = %s", (scrape_run_id,))
        cur.executemany(
            """
            INSERT INTO reporting.part_number_filter_review (
                source_domain,
                row_kind,
                source_sync_run_id,
                scrape_run_id,
                product_id,
                pohoda_id,
                search_request_id,
                observation_id,
                source_database,
                product_name,
                search_identifier,
                search_identifier_normalized,
                raw_part_number,
                normalized_part_number,
                normalized_base_part_number,
                matched_suffixes,
                variant_scope,
                classification_reason,
                competitor_product_name,
                product_url,
                match_type,
                match_confidence,
                row_ordinal,
                generated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            [
                (
                    row["source_domain"],
                    row["row_kind"],
                    row["source_sync_run_id"],
                    row["scrape_run_id"],
                    row["product_id"],
                    row["pohoda_id"],
                    row["search_request_id"],
                    row["observation_id"],
                    row["source_database"],
                    row["product_name"],
                    row["search_identifier"],
                    row["search_identifier_normalized"],
                    row["raw_part_number"],
                    row["normalized_part_number"],
                    row["normalized_base_part_number"],
                    row["matched_suffixes"],
                    row["variant_scope"],
                    row["classification_reason"],
                    row["competitor_product_name"],
                    row["product_url"],
                    row["match_type"],
                    row["match_confidence"],
                    row["row_ordinal"],
                    row["generated_at"],
                )
                for row in rows
            ],
        )


def print_preview(rows: list[dict[str, object]]) -> None:
    sandix_original = sum(1 for row in rows if row["source_domain"] == "SANDIX" and row["variant_scope"] == "ORIGINAL")
    sandix_alternative = sum(1 for row in rows if row["source_domain"] == "SANDIX" and row["variant_scope"] == "ALTERNATIVE")
    profibagr_original = sum(
        1
        for row in rows
        if row["source_domain"] == "PROFIBAGR" and row["row_kind"] == "OFFER_OBSERVATION" and row["variant_scope"] == "ORIGINAL"
    )
    profibagr_alternative = sum(
        1
        for row in rows
        if row["source_domain"] == "PROFIBAGR" and row["row_kind"] == "OFFER_OBSERVATION" and row["variant_scope"] == "ALTERNATIVE"
    )
    unresolved = sum(1 for row in rows if row["variant_scope"] == "UNRESOLVED")
    print(f"Sandix tokens: {sandix_original} original, {sandix_alternative} alternative")
    print(f"Profibagr observations: {profibagr_original} original, {profibagr_alternative} alternative, {unresolved} unresolved")
    print("Sample filter rows:")
    for row in rows[:10]:
        print(
            f"- {row['source_domain']} / {row['row_kind']} / {row['variant_scope']}: {row['raw_part_number']} -> {row['normalized_base_part_number']} ({row['classification_reason']})"
        )


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent / ".env")
    load_dotenv(Path(__file__).resolve().parent.parent / "profibagr-scraper" / ".env")

    try:
        with connect(get_env_default("PG_MONITOR_DB", "sandix_price_monitor"), "PG_MONITOR") as monitor_conn, connect(
            get_env_default("PG_ANALYTICS_DB", "sandix_price_analytics"), "PG_ANALYTICS"
        ) as analytics_conn:
            ensure_reporting_objects(analytics_conn)
            seed_variant_suffix_catalog(analytics_conn, ROOT / "rozliseni_alternativ.xlsx")
            suffixes = fetch_variant_suffixes(analytics_conn)
            source_rows = fetch_source_rows(monitor_conn)
            scrape_run = fetch_latest_successful_scrape_run(monitor_conn)
            request_rows = fetch_request_product_rows(monitor_conn, scrape_run["run_id"])
            observation_rows = fetch_observation_rows(monitor_conn, scrape_run["run_id"])
            generated_at = datetime.now(timezone.utc)

            review_rows = []
            review_rows.extend(build_source_rows(source_rows, suffixes, generated_at))
            review_rows.extend(build_request_rows(request_rows, suffixes, scrape_run["run_id"], generated_at))
            review_rows.extend(build_observation_rows(observation_rows, suffixes, scrape_run["run_id"], generated_at))

            source_sync_run_id = source_rows[0]["last_sync_run_id"] if source_rows else None
            with analytics_conn.transaction():
                write_snapshot(analytics_conn, review_rows, source_sync_run_id, scrape_run["run_id"])

            print_preview(review_rows)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Part-number filter ETL failed: {exc}", file=sys.stderr)
        return 1

    print("Part-number filter snapshot stored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
