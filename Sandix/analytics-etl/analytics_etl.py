from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sandix.analytics import (  # noqa: E402
    ANALYTICS_DDL,
    COMPETITOR_CODE,
    COMPETITOR_NAME,
    VALID_SEARCH_STATUSES,
    normalize_search_status,
    price_gap,
    price_gap_pct_vs_competitor,
    summarise_price_comparison,
)
from sandix.alternatives import (  # noqa: E402
    VARIANT_ANALYTICS_DDL,
    classify_competitor_variant,
    classify_sandix_variant,
    load_alternative_suffixes,
    load_known_identifiers,
    normalize_variant_token,
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
        for statement in ANALYTICS_DDL + VARIANT_ANALYTICS_DDL:
            cur.execute(statement)


def fetch_latest_run(conn: psycopg.Connection) -> dict[str, object]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                run_id,
                competitor_code,
                competitor_name,
                started_at,
                finished_at,
                queue_count
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


def fetch_known_identifiers(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT source_identifier
            FROM core.product_search_identifier_v
            WHERE source_identifier IS NOT NULL
              AND btrim(source_identifier) <> ''
            """
        )
        return load_known_identifiers([row[0] for row in cur.fetchall()])


def fetch_raw_offer_rows(conn: psycopg.Connection, source_run_id: uuid.UUID) -> list[dict[str, object]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH request_products AS (
                SELECT DISTINCT
                    sr.search_request_id,
                    sr.searched_identifier,
                    sp.product_id,
                    sp.source_identifier
                FROM scraper.search_request sr
                JOIN scraper.search_request_product sp
                  ON sp.search_request_id = sr.search_request_id
                WHERE sr.run_id = %s
                  AND sr.status = 'OK'
            )
            SELECT
                rp.search_request_id,
                rp.product_id,
                rp.searched_identifier,
                rp.source_identifier,
                cp.product_name,
                cp.selling_price_net AS sandix_price_net,
                cp.selling_price_gross AS sandix_price_gross,
                oo.observation_id,
                oo.found_identifier,
                oo.found_identifier_norm,
                oo.competitor_product_name,
                oo.price_without_vat,
                oo.price_with_vat,
                oo.product_url
            FROM request_products rp
            JOIN core.product_current_v cp
              ON cp.product_id = rp.product_id
            JOIN scraper.offer_observation oo
              ON oo.search_request_id = rp.search_request_id
            ORDER BY rp.product_id, oo.price_with_vat ASC NULLS LAST, oo.price_without_vat ASC NULLS LAST, oo.observation_id ASC
            """,
            (source_run_id,),
        )
        columns = [desc.name for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def fetch_search_status_map(conn: psycopg.Connection, source_run_id: uuid.UUID) -> dict[int, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT search_request_id, status
            FROM scraper.search_request
            WHERE run_id = %s
            """,
            (source_run_id,),
        )
        return {int(search_request_id): normalize_search_status(status) for search_request_id, status in cur.fetchall()}


def classify_offer_rows(
    raw_rows: list[dict[str, object]],
    known_identifiers: set[str],
    suffixes: list[str],
) -> tuple[dict[str, list[dict[str, object]]], int]:
    scoped_rows: dict[str, list[dict[str, object]]] = {"ORIGINAL": [], "ALTERNATIVE": []}
    mismatch_count = 0

    for row in raw_rows:
        sandix_match = classify_sandix_variant(row["source_identifier"], known_identifiers, suffixes)
        competitor_match = classify_competitor_variant(
            row["found_identifier"],
            row["competitor_product_name"],
            row["product_url"],
            suffixes,
        )
        if sandix_match.scope != competitor_match.scope:
            mismatch_count += 1

        scoped_row = dict(row)
        scoped_row["comparison_scope"] = competitor_match.scope
        scoped_row["sandix_variant_suffix"] = sandix_match.matched_suffix
        scoped_row["competitor_variant_suffix"] = competitor_match.matched_suffix
        scoped_rows[competitor_match.scope].append(scoped_row)

    return scoped_rows, mismatch_count


def build_scope_search_status_rows(
    request_ids: set[int],
    status_map: dict[int, str],
    comparison_scope: str,
) -> list[dict[str, object]]:
    counts = {status: 0 for status in VALID_SEARCH_STATUSES}
    for request_id in request_ids:
        counts[status_map.get(request_id, "ERROR")] += 1

    total = sum(counts.values()) or 1
    return [
        {
            "comparison_scope": comparison_scope,
            "search_status": status,
            "request_count": counts[status],
            "request_pct": (Decimal(counts[status]) / Decimal(total) * Decimal("100")).quantize(Decimal("0.01")),
        }
        for status in VALID_SEARCH_STATUSES
    ]


def build_scope_price_rows(rows: list[dict[str, object]], comparison_scope: str) -> list[dict[str, object]]:
    grouped: dict[int, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(int(row["product_id"]), []).append(row)

    comparison_rows: list[dict[str, object]] = []
    for product_id, group_rows in grouped.items():
        valid_rows = [row for row in group_rows if row["price_with_vat"] is not None and row["price_with_vat"] > 0]
        if not valid_rows:
            continue
        best_row = min(
            valid_rows,
            key=lambda row: (
                row["price_with_vat"],
                row["price_without_vat"] if row["price_without_vat"] is not None else Decimal("Infinity"),
                row["observation_id"],
            ),
        )
        comparison_rows.append(
            {
                "comparison_scope": comparison_scope,
                "product_id": product_id,
                "source_identifier": best_row["source_identifier"],
                "searched_identifier": best_row["searched_identifier"],
                "product_name": best_row["product_name"],
                "sandix_price_net": best_row["sandix_price_net"],
                "sandix_price_gross": best_row["sandix_price_gross"],
                "profibagr_price_net": best_row["price_without_vat"],
                "profibagr_price_gross": best_row["price_with_vat"],
                "profibagr_product_url": best_row["product_url"],
                "search_request_count": len({row["search_request_id"] for row in group_rows}),
                "raw_offer_count": len(group_rows),
                "valid_offer_count": len(valid_rows),
                "invalid_offer_count": len(group_rows) - len(valid_rows),
            }
        )

    for row in comparison_rows:
        row["price_gap_net"] = price_gap(row["sandix_price_net"], row["profibagr_price_net"])
        row["price_gap_gross"] = price_gap(row["sandix_price_gross"], row["profibagr_price_gross"])
        row["price_gap_pct_vs_competitor"] = price_gap_pct_vs_competitor(row["sandix_price_gross"], row["profibagr_price_gross"])

    comparison_rows.sort(
        key=lambda row: (
            row["price_gap_pct_vs_competitor"] is not None,
            row["price_gap_pct_vs_competitor"] if row["price_gap_pct_vs_competitor"] is not None else Decimal("-Infinity"),
            row["price_gap_gross"] if row["price_gap_gross"] is not None else Decimal("-Infinity"),
            row["product_name"] or "",
        ),
        reverse=True,
    )
    return comparison_rows


def build_scope_batch_kpi(
    source_run: dict[str, object],
    comparison_scope: str,
    comparison_rows: list[dict[str, object]],
    search_status_rows: list[dict[str, object]],
    request_count: int,
    raw_offer_count: int,
    mismatch_offer_count: int,
) -> dict[str, object]:
    status_counts = {row["search_status"]: int(row["request_count"]) for row in search_status_rows}
    comparison_metrics = summarise_price_comparison(comparison_rows)
    valid_offer_count = sum(int(row["valid_offer_count"]) for row in comparison_rows)
    invalid_offer_count = sum(int(row["invalid_offer_count"]) for row in comparison_rows)

    return {
        "source_run_id": source_run["run_id"],
        "comparison_scope": comparison_scope,
        "competitor_code": source_run["competitor_code"] or COMPETITOR_CODE,
        "competitor_name": source_run["competitor_name"] or COMPETITOR_NAME,
        "generated_at": datetime.now(timezone.utc),
        "batch_started_at": source_run["started_at"],
        "batch_finished_at": source_run["finished_at"],
        "queue_count": request_count,
        "request_count": request_count,
        "search_success_count": status_counts.get("OK", 0),
        "not_found_count": status_counts.get("NOT_FOUND", 0),
        "error_count": status_counts.get("ERROR", 0),
        "raw_offer_count": raw_offer_count,
        "valid_offer_count": valid_offer_count,
        "invalid_offer_count": invalid_offer_count,
        "mismatch_offer_count": mismatch_offer_count,
        "matched_product_count": int(comparison_metrics["matched_product_count"]),
        "sandix_more_expensive_count": int(comparison_metrics["sandix_more_expensive_count"]),
        "sandix_cheaper_count": int(comparison_metrics["sandix_cheaper_count"]),
        "equal_price_count": int(comparison_metrics["equal_price_count"]),
        "average_gap_pct_vs_competitor": comparison_metrics["average_gap_pct_vs_competitor"],
        "max_positive_gap_pct_vs_competitor": comparison_metrics["max_positive_gap_pct_vs_competitor"],
        "max_negative_gap_pct_vs_competitor": comparison_metrics["max_negative_gap_pct_vs_competitor"],
    }


def write_variant_snapshot(
    conn: psycopg.Connection,
    batch_rows: list[dict[str, object]],
    comparison_rows: list[dict[str, object]],
    search_status_rows: list[dict[str, object]],
) -> None:
    source_run_id = batch_rows[0]["source_run_id"]
    generated_at = batch_rows[0]["generated_at"]
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM reporting.profibagr_variant_price_comparison WHERE source_run_id = %s",
            (source_run_id,),
        )
        cur.execute(
            "DELETE FROM reporting.profibagr_variant_search_status WHERE source_run_id = %s",
            (source_run_id,),
        )
        cur.execute(
            "DELETE FROM reporting.profibagr_variant_batch_kpi WHERE source_run_id = %s",
            (source_run_id,),
        )
        cur.executemany(
            """
            INSERT INTO reporting.profibagr_variant_batch_kpi (
                source_run_id,
                comparison_scope,
                competitor_code,
                competitor_name,
                generated_at,
                batch_started_at,
                batch_finished_at,
                request_count,
                search_success_count,
                not_found_count,
                error_count,
                raw_offer_count,
                valid_offer_count,
                invalid_offer_count,
                mismatch_offer_count,
                matched_product_count,
                sandix_more_expensive_count,
                sandix_cheaper_count,
                equal_price_count,
                average_gap_pct_vs_competitor,
                max_positive_gap_pct_vs_competitor,
                max_negative_gap_pct_vs_competitor
            ) VALUES (
                %(source_run_id)s,
                %(comparison_scope)s,
                %(competitor_code)s,
                %(competitor_name)s,
                %(generated_at)s,
                %(batch_started_at)s,
                %(batch_finished_at)s,
                %(request_count)s,
                %(search_success_count)s,
                %(not_found_count)s,
                %(error_count)s,
                %(raw_offer_count)s,
                %(valid_offer_count)s,
                %(invalid_offer_count)s,
                %(mismatch_offer_count)s,
                %(matched_product_count)s,
                %(sandix_more_expensive_count)s,
                %(sandix_cheaper_count)s,
                %(equal_price_count)s,
                %(average_gap_pct_vs_competitor)s,
                %(max_positive_gap_pct_vs_competitor)s,
                %(max_negative_gap_pct_vs_competitor)s
            )
            """,
            batch_rows,
        )
        cur.executemany(
            """
            INSERT INTO reporting.profibagr_variant_price_comparison (
                source_run_id,
                comparison_scope,
                product_id,
                source_identifier,
                searched_identifier,
                product_name,
                sandix_price_net,
                sandix_price_gross,
                profibagr_price_net,
                profibagr_price_gross,
                profibagr_product_url,
                price_gap_net,
                price_gap_gross,
                price_gap_pct_vs_competitor,
                raw_offer_count,
                valid_offer_count,
                invalid_offer_count,
                search_request_count,
                generated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            [
                (
                    source_run_id,
                    row["comparison_scope"],
                    row["product_id"],
                    row["source_identifier"],
                    row["searched_identifier"],
                    row["product_name"],
                    row["sandix_price_net"],
                    row["sandix_price_gross"],
                    row["profibagr_price_net"],
                    row["profibagr_price_gross"],
                    row["profibagr_product_url"],
                    row["price_gap_net"],
                    row["price_gap_gross"],
                    row["price_gap_pct_vs_competitor"],
                    row["raw_offer_count"],
                    row["valid_offer_count"],
                    row["invalid_offer_count"],
                    row["search_request_count"],
                    generated_at,
                )
                for row in comparison_rows
            ],
        )
        cur.executemany(
            """
            INSERT INTO reporting.profibagr_variant_search_status (
                source_run_id,
                comparison_scope,
                search_status,
                request_count,
                request_pct,
                generated_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    source_run_id,
                    row["comparison_scope"],
                    row["search_status"],
                    row["request_count"],
                    row["request_pct"],
                    generated_at,
                )
                for row in search_status_rows
            ],
        )


def print_scope_preview(batch_rows: list[dict[str, object]], comparison_rows_by_scope: dict[str, list[dict[str, object]]]) -> None:
    for batch_row in batch_rows:
        scope = batch_row["comparison_scope"]
        comparison_rows = comparison_rows_by_scope[scope]
        print(
            f"{scope}: {batch_row['matched_product_count']} matched products from {batch_row['search_success_count']} successful requests"
        )
        print(
            f"  Coverage: {batch_row['search_success_count']} OK, {batch_row['not_found_count']} NOT_FOUND, {batch_row['error_count']} ERROR"
        )
        print(
            f"  Offers: {batch_row['raw_offer_count']} raw, {batch_row['valid_offer_count']} valid, {batch_row['invalid_offer_count']} excluded, {batch_row['mismatch_offer_count']} mismatched"
        )
        for row in comparison_rows[:5]:
            print(
                f"  - {row['searched_identifier']}: Sandix {row['sandix_price_gross']} vs Profibagr {row['profibagr_price_gross']} => gap {row['price_gap_gross']} ({row['price_gap_pct_vs_competitor']}%)"
            )


def fetch_search_status_rows(conn: psycopg.Connection, source_run_id: uuid.UUID) -> list[dict[str, object]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                CASE
                    WHEN status = 'OK' THEN 'OK'
                    WHEN status = 'NOT_FOUND' THEN 'NOT_FOUND'
                    ELSE 'ERROR'
                END AS search_status,
                COUNT(*)::int AS request_count
            FROM scraper.search_request
            WHERE run_id = %s
            GROUP BY 1
            """,
            (source_run_id,),
        )
        columns = [desc.name for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    counts = {row["search_status"]: int(row["request_count"]) for row in rows}
    total = sum(counts.values())
    if total == 0:
        total = 1
    filled_rows = []
    for status in VALID_SEARCH_STATUSES:
        request_count = counts.get(status, 0)
        filled_rows.append(
            {
                "search_status": status,
                "request_count": request_count,
                "request_pct": (Decimal(request_count) / Decimal(total) * Decimal("100")).quantize(Decimal("0.01")),
            }
        )
    return filled_rows


def fetch_price_comparison_rows(conn: psycopg.Connection, source_run_id: uuid.UUID) -> list[dict[str, object]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH request_products AS (
                SELECT DISTINCT
                    sr.search_request_id,
                    sr.searched_identifier,
                    sp.product_id,
                    sp.source_identifier
                FROM scraper.search_request sr
                JOIN scraper.search_request_product sp
                  ON sp.search_request_id = sr.search_request_id
                WHERE sr.run_id = %s
                  AND sr.status = 'OK'
            ),
            raw_matches AS (
                SELECT
                    rp.search_request_id,
                    rp.product_id,
                    rp.searched_identifier,
                    rp.source_identifier,
                    cp.product_name,
                    cp.selling_price_net AS sandix_price_net,
                    cp.selling_price_gross AS sandix_price_gross,
                    oo.observation_id,
                    oo.price_without_vat,
                    oo.price_with_vat,
                    oo.product_url
                FROM request_products rp
                JOIN core.product_current_v cp
                  ON cp.product_id = rp.product_id
                JOIN scraper.offer_observation oo
                  ON oo.search_request_id = rp.search_request_id
            ),
            best_offer AS (
                SELECT DISTINCT ON (product_id)
                    product_id,
                    source_identifier,
                    searched_identifier,
                    product_name,
                    sandix_price_net,
                    sandix_price_gross,
                    price_without_vat,
                    price_with_vat,
                    product_url
                FROM raw_matches
                WHERE price_with_vat > 0
                ORDER BY product_id, price_with_vat ASC, price_without_vat ASC, observation_id ASC
            ),
            counts AS (
                SELECT
                    product_id,
                    COUNT(DISTINCT search_request_id)::int AS search_request_count,
                    COUNT(DISTINCT observation_id)::int AS raw_offer_count,
                    COUNT(DISTINCT observation_id) FILTER (WHERE price_with_vat > 0)::int AS valid_offer_count,
                    COUNT(DISTINCT observation_id) FILTER (WHERE price_with_vat IS NULL OR price_with_vat <= 0)::int AS invalid_offer_count
                FROM raw_matches
                GROUP BY product_id
            )
            SELECT
                c.product_id,
                b.source_identifier,
                b.searched_identifier,
                b.product_name,
                b.sandix_price_net,
                b.sandix_price_gross,
                b.price_without_vat AS profibagr_price_net,
                b.price_with_vat AS profibagr_price_gross,
                b.product_url AS profibagr_product_url,
                c.search_request_count,
                c.raw_offer_count,
                c.valid_offer_count,
                c.invalid_offer_count
            FROM counts c
            JOIN best_offer b
              ON b.product_id = c.product_id
            ORDER BY b.product_name, b.product_id
            """,
            (source_run_id,),
        )
        columns = [desc.name for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    for row in rows:
        row["price_gap_net"] = price_gap(row["sandix_price_net"], row["profibagr_price_net"])
        row["price_gap_gross"] = price_gap(row["sandix_price_gross"], row["profibagr_price_gross"])
        row["price_gap_pct_vs_competitor"] = price_gap_pct_vs_competitor(row["sandix_price_gross"], row["profibagr_price_gross"])
    rows.sort(
        key=lambda row: (
            row["price_gap_pct_vs_competitor"] is not None,
            row["price_gap_pct_vs_competitor"] if row["price_gap_pct_vs_competitor"] is not None else Decimal("-Infinity"),
            row["price_gap_gross"] if row["price_gap_gross"] is not None else Decimal("-Infinity"),
            row["product_name"] or "",
        ),
        reverse=True,
    )
    return rows


def fetch_offer_counts(conn: psycopg.Connection, source_run_id: uuid.UUID) -> tuple[int, int, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*)::int AS raw_offer_count,
                COUNT(*) FILTER (WHERE oo.price_with_vat > 0)::int AS valid_offer_count,
                COUNT(*) FILTER (WHERE oo.price_with_vat IS NULL OR oo.price_with_vat <= 0)::int AS invalid_offer_count
            FROM scraper.offer_observation oo
            JOIN scraper.search_request sr
              ON sr.search_request_id = oo.search_request_id
            WHERE sr.run_id = %s
            """,
            (source_run_id,),
        )
        raw_offer_count, valid_offer_count, invalid_offer_count = cur.fetchone()
    return int(raw_offer_count), int(valid_offer_count), int(invalid_offer_count)


def build_batch_kpi(
    source_run: dict[str, object],
    comparison_rows: list[dict[str, object]],
    search_status_rows: list[dict[str, object]],
    offer_counts: tuple[int, int, int],
) -> dict[str, object]:
    status_counts = {row["search_status"]: int(row["request_count"]) for row in search_status_rows}
    raw_offer_count, valid_offer_count, invalid_offer_count = offer_counts
    comparison_metrics = summarise_price_comparison(comparison_rows)

    return {
        "source_run_id": source_run["run_id"],
        "competitor_code": source_run["competitor_code"] or COMPETITOR_CODE,
        "competitor_name": source_run["competitor_name"] or COMPETITOR_NAME,
        "generated_at": datetime.now(timezone.utc),
        "batch_started_at": source_run["started_at"],
        "batch_finished_at": source_run["finished_at"],
        "queue_count": int(source_run["queue_count"] or 0),
        "search_success_count": status_counts.get("OK", 0),
        "not_found_count": status_counts.get("NOT_FOUND", 0),
        "error_count": status_counts.get("ERROR", 0),
        "raw_offer_count": raw_offer_count,
        "valid_offer_count": valid_offer_count,
        "invalid_offer_count": invalid_offer_count,
        "matched_product_count": int(comparison_metrics["matched_product_count"]),
        "sandix_more_expensive_count": int(comparison_metrics["sandix_more_expensive_count"]),
        "sandix_cheaper_count": int(comparison_metrics["sandix_cheaper_count"]),
        "equal_price_count": int(comparison_metrics["equal_price_count"]),
        "average_gap_pct_vs_competitor": comparison_metrics["average_gap_pct_vs_competitor"],
        "max_positive_gap_pct_vs_competitor": comparison_metrics["max_positive_gap_pct_vs_competitor"],
        "max_negative_gap_pct_vs_competitor": comparison_metrics["max_negative_gap_pct_vs_competitor"],
    }


def write_snapshot(
    conn: psycopg.Connection,
    source_run: dict[str, object],
    batch_kpi: dict[str, object],
    comparison_rows: list[dict[str, object]],
    search_status_rows: list[dict[str, object]],
) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM reporting.profibagr_price_comparison WHERE source_run_id = %s", (source_run["run_id"],))
        cur.execute("DELETE FROM reporting.profibagr_search_status WHERE source_run_id = %s", (source_run["run_id"],))
        cur.execute("DELETE FROM reporting.profibagr_batch_kpi WHERE source_run_id = %s", (source_run["run_id"],))
        cur.execute(
            """
            INSERT INTO reporting.profibagr_batch_kpi (
                source_run_id,
                competitor_code,
                competitor_name,
                generated_at,
                batch_started_at,
                batch_finished_at,
                queue_count,
                search_success_count,
                not_found_count,
                error_count,
                raw_offer_count,
                valid_offer_count,
                invalid_offer_count,
                matched_product_count,
                sandix_more_expensive_count,
                sandix_cheaper_count,
                equal_price_count,
                average_gap_pct_vs_competitor,
                max_positive_gap_pct_vs_competitor,
                max_negative_gap_pct_vs_competitor
            ) VALUES (
                %(source_run_id)s,
                %(competitor_code)s,
                %(competitor_name)s,
                %(generated_at)s,
                %(batch_started_at)s,
                %(batch_finished_at)s,
                %(queue_count)s,
                %(search_success_count)s,
                %(not_found_count)s,
                %(error_count)s,
                %(raw_offer_count)s,
                %(valid_offer_count)s,
                %(invalid_offer_count)s,
                %(matched_product_count)s,
                %(sandix_more_expensive_count)s,
                %(sandix_cheaper_count)s,
                %(equal_price_count)s,
                %(average_gap_pct_vs_competitor)s,
                %(max_positive_gap_pct_vs_competitor)s,
                %(max_negative_gap_pct_vs_competitor)s
            )
            """,
            batch_kpi,
        )
        cur.executemany(
            """
            INSERT INTO reporting.profibagr_price_comparison (
                source_run_id,
                product_id,
                source_identifier,
                searched_identifier,
                product_name,
                sandix_price_net,
                sandix_price_gross,
                profibagr_price_net,
                profibagr_price_gross,
                profibagr_product_url,
                price_gap_net,
                price_gap_gross,
                price_gap_pct_vs_competitor,
                raw_offer_count,
                valid_offer_count,
                invalid_offer_count,
                search_request_count,
                generated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            [
                (
                    source_run["run_id"],
                    row["product_id"],
                    row["source_identifier"],
                    row["searched_identifier"],
                    row["product_name"],
                    row["sandix_price_net"],
                    row["sandix_price_gross"],
                    row["profibagr_price_net"],
                    row["profibagr_price_gross"],
                    row["profibagr_product_url"],
                    row["price_gap_net"],
                    row["price_gap_gross"],
                    row["price_gap_pct_vs_competitor"],
                    row["raw_offer_count"],
                    row["valid_offer_count"],
                    row["invalid_offer_count"],
                    row["search_request_count"],
                    batch_kpi["generated_at"],
                )
                for row in comparison_rows
            ],
        )
        cur.executemany(
            """
            INSERT INTO reporting.profibagr_search_status (
                source_run_id,
                search_status,
                request_count,
                request_pct,
                generated_at
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (
                    source_run["run_id"],
                    row["search_status"],
                    row["request_count"],
                    row["request_pct"],
                    batch_kpi["generated_at"],
                )
                for row in search_status_rows
            ],
        )


def print_preview(source_run: dict[str, object], batch_kpi: dict[str, object], comparison_rows: list[dict[str, object]]) -> None:
    print(
        f"Latest Profibagr run {source_run['run_id']} produced {batch_kpi['matched_product_count']} matched products from {batch_kpi['search_success_count']} successful search requests"
    )
    print(
        f"Coverage: {batch_kpi['search_success_count']} OK, {batch_kpi['not_found_count']} NOT_FOUND, {batch_kpi['error_count']} ERROR"
    )
    print(
        f"Offers: {batch_kpi['raw_offer_count']} raw, {batch_kpi['valid_offer_count']} valid, {batch_kpi['invalid_offer_count']} excluded"
    )
    print("Top price gaps:")
    for row in comparison_rows[:10]:
        print(
            f"- {row['searched_identifier']}: Sandix {row['sandix_price_gross']} vs Profibagr {row['profibagr_price_gross']} => gap {row['price_gap_gross']} ({row['price_gap_pct_vs_competitor']}%)"
        )


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent / ".env")
    load_dotenv(Path(__file__).resolve().parent.parent / "profibagr-scraper" / ".env")

    try:
        with connect(get_env_default("PG_MONITOR_DB", "sandix_price_monitor"), "PG_MONITOR") as monitor_conn, connect(
            get_env_default("PG_ANALYTICS_DB", "sandix_price_analytics"), "PG_ANALYTICS"
        ) as analytics_conn:
            ensure_reporting_objects(analytics_conn)
            source_run = fetch_latest_run(monitor_conn)
            suffixes = load_alternative_suffixes(ROOT / "rozliseni_alternativ.xlsx")
            known_identifiers = fetch_known_identifiers(monitor_conn)
            raw_rows = fetch_raw_offer_rows(monitor_conn, source_run["run_id"])
            status_map = fetch_search_status_map(monitor_conn, source_run["run_id"])
            scoped_rows, mismatch_count = classify_offer_rows(raw_rows, known_identifiers, suffixes)

            batch_rows: list[dict[str, object]] = []
            comparison_rows_by_scope: dict[str, list[dict[str, object]]] = {}
            search_status_rows_by_scope: dict[str, list[dict[str, object]]] = {}

            for scope in ("ORIGINAL", "ALTERNATIVE"):
                scope_rows = scoped_rows[scope]
                request_ids = {int(row["search_request_id"]) for row in scope_rows}
                comparison_rows = build_scope_price_rows(scope_rows, scope)
                search_status_rows = build_scope_search_status_rows(request_ids, status_map, scope)
                batch_rows.append(
                    build_scope_batch_kpi(
                        source_run,
                        scope,
                        comparison_rows,
                        search_status_rows,
                        len(request_ids),
                        len(scope_rows),
                        len(raw_rows) - len(scope_rows),
                    )
                )
                comparison_rows_by_scope[scope] = comparison_rows
                search_status_rows_by_scope[scope] = search_status_rows

            with analytics_conn.transaction():
                write_snapshot(
                    analytics_conn,
                    source_run,
                    batch_rows[0],
                    comparison_rows_by_scope["ORIGINAL"],
                    search_status_rows_by_scope["ORIGINAL"],
                )
                write_variant_snapshot(
                    analytics_conn,
                    batch_rows,
                    comparison_rows_by_scope["ORIGINAL"] + comparison_rows_by_scope["ALTERNATIVE"],
                    search_status_rows_by_scope["ORIGINAL"] + search_status_rows_by_scope["ALTERNATIVE"],
                )

            print_scope_preview(batch_rows, comparison_rows_by_scope)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Analytics build failed: {exc}", file=sys.stderr)
        return 1

    print(f"Analytics snapshot stored for source run {source_run['run_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
