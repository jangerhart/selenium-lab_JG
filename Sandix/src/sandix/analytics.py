from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


DEFAULT_COMPETITOR_CODE = "PROFIBAGR"
DEFAULT_COMPETITOR_NAME = "Profibagr"
VALID_SEARCH_STATUSES = ("OK", "NOT_FOUND", "ERROR")

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")


def quantize(value: Decimal | None, quantum: Decimal) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def normalize_search_status(raw_status: str | None) -> str:
    if raw_status == "OK":
        return "OK"
    if raw_status == "NOT_FOUND":
        return "NOT_FOUND"
    return "ERROR"


def price_gap(sandix_price: Decimal | None, competitor_price: Decimal | None) -> Decimal | None:
    if sandix_price is None or competitor_price is None or competitor_price <= 0:
        return None
    return quantize(sandix_price - competitor_price, FOURPLACES)


def price_gap_pct_vs_competitor(
    sandix_price: Decimal | None,
    competitor_price: Decimal | None,
) -> Decimal | None:
    if sandix_price is None or competitor_price is None or competitor_price <= 0:
        return None
    return quantize(((sandix_price - competitor_price) / competitor_price) * Decimal("100"), TWOPLACES)


def gap_bucket(price_gap_value: Decimal | None) -> str | None:
    if price_gap_value is None:
        return None
    if price_gap_value > 0:
        return "SANDIX_MORE_EXPENSIVE"
    if price_gap_value < 0:
        return "SANDIX_CHEAPER"
    return "EQUAL"


def summarise_price_comparison(rows: list[dict[str, object]]) -> dict[str, object]:
    valid_rows = [row for row in rows if row.get("price_gap_pct_vs_competitor") is not None]
    sandix_more_expensive_count = sum(1 for row in valid_rows if row["price_gap_gross"] is not None and row["price_gap_gross"] > 0)
    sandix_cheaper_count = sum(1 for row in valid_rows if row["price_gap_gross"] is not None and row["price_gap_gross"] < 0)
    equal_price_count = sum(1 for row in valid_rows if row["price_gap_gross"] == 0)
    positive_gaps = [row["price_gap_pct_vs_competitor"] for row in valid_rows if row["price_gap_pct_vs_competitor"] > 0]
    negative_gaps = [row["price_gap_pct_vs_competitor"] for row in valid_rows if row["price_gap_pct_vs_competitor"] < 0]
    all_gaps = [row["price_gap_pct_vs_competitor"] for row in valid_rows]

    return {
        "matched_product_count": len(rows),
        "sandix_more_expensive_count": sandix_more_expensive_count,
        "sandix_cheaper_count": sandix_cheaper_count,
        "equal_price_count": equal_price_count,
        "average_gap_pct_vs_competitor": quantize((sum(all_gaps) / len(all_gaps)) if all_gaps else None, TWOPLACES),
        "max_positive_gap_pct_vs_competitor": quantize(max(positive_gaps) if positive_gaps else None, TWOPLACES),
        "max_negative_gap_pct_vs_competitor": quantize(min(negative_gaps) if negative_gaps else None, TWOPLACES),
    }


ANALYTICS_DDL = [
    "CREATE SCHEMA IF NOT EXISTS reporting",
    """
    CREATE TABLE IF NOT EXISTS reporting.competitor_batch_kpi (
        source_run_id uuid NOT NULL,
        competitor_code text NOT NULL,
        competitor_name text NOT NULL,
        comparison_scope text NOT NULL,
        generated_at timestamptz NOT NULL,
        batch_started_at timestamptz NOT NULL,
        batch_finished_at timestamptz,
        queue_count integer NOT NULL,
        search_success_count integer NOT NULL,
        not_found_count integer NOT NULL,
        error_count integer NOT NULL,
        raw_offer_count integer NOT NULL,
        valid_offer_count integer NOT NULL,
        invalid_offer_count integer NOT NULL,
        matched_product_count integer NOT NULL,
        sandix_more_expensive_count integer NOT NULL,
        sandix_cheaper_count integer NOT NULL,
        equal_price_count integer NOT NULL,
        average_gap_pct_vs_competitor numeric(10,2),
        max_positive_gap_pct_vs_competitor numeric(10,2),
        max_negative_gap_pct_vs_competitor numeric(10,2),
        PRIMARY KEY (source_run_id, competitor_code, comparison_scope)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reporting.competitor_price_comparison (
        source_run_id uuid NOT NULL,
        competitor_code text NOT NULL,
        competitor_name text NOT NULL,
        comparison_scope text NOT NULL,
        product_id bigint NOT NULL,
        sandix_part_number text,
        competitor_part_number text,
        source_identifier text,
        searched_identifier text NOT NULL,
        product_name text,
        sandix_price_net numeric(18,4),
        sandix_price_gross numeric(18,4),
        competitor_price_net numeric(18,4),
        competitor_price_gross numeric(18,4),
        competitor_product_url text,
        price_gap_net numeric(18,4),
        price_gap_gross numeric(18,4),
        price_gap_pct_vs_competitor numeric(10,2),
        raw_offer_count integer NOT NULL,
        valid_offer_count integer NOT NULL,
        invalid_offer_count integer NOT NULL,
        search_request_count integer NOT NULL,
        generated_at timestamptz NOT NULL,
        PRIMARY KEY (source_run_id, competitor_code, comparison_scope, product_id)
    )
    """,
    """
    ALTER TABLE reporting.competitor_price_comparison
    ADD COLUMN IF NOT EXISTS sandix_part_number text
    """,
    """
    ALTER TABLE reporting.competitor_price_comparison
    ADD COLUMN IF NOT EXISTS competitor_part_number text
    """,
    """
    CREATE TABLE IF NOT EXISTS reporting.competitor_search_status (
        source_run_id uuid NOT NULL,
        competitor_code text NOT NULL,
        competitor_name text NOT NULL,
        comparison_scope text NOT NULL,
        search_status text NOT NULL,
        request_count integer NOT NULL,
        request_pct numeric(10,2) NOT NULL,
        generated_at timestamptz NOT NULL,
        PRIMARY KEY (source_run_id, competitor_code, comparison_scope, search_status)
    )
    """,
    """
    CREATE OR REPLACE VIEW reporting.competitor_latest_batch_v AS
    WITH ranked AS (
        SELECT
            source_run_id,
            competitor_code,
            competitor_name,
            comparison_scope,
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
            max_negative_gap_pct_vs_competitor,
            row_number() OVER (
                PARTITION BY competitor_code, comparison_scope
                ORDER BY generated_at DESC, batch_finished_at DESC NULLS LAST, source_run_id DESC
            ) AS rn
        FROM reporting.competitor_batch_kpi
    )
    SELECT
        source_run_id,
        competitor_code,
        competitor_name,
        comparison_scope,
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
    FROM ranked
    WHERE rn = 1
    ORDER BY competitor_code
    """,
    """
    CREATE OR REPLACE VIEW reporting.competitor_latest_price_comparison_v AS
    WITH latest_runs AS (
        SELECT DISTINCT ON (competitor_code, comparison_scope)
            source_run_id,
            competitor_code,
            comparison_scope
        FROM reporting.competitor_batch_kpi
        ORDER BY competitor_code, comparison_scope, generated_at DESC, batch_finished_at DESC NULLS LAST, source_run_id DESC
    )
    SELECT
        p.source_run_id,
        p.competitor_code,
        p.competitor_name,
        p.comparison_scope,
        p.product_id,
        p.source_identifier,
        p.searched_identifier,
        p.product_name,
        p.sandix_price_net,
        p.sandix_price_gross,
        p.competitor_price_net,
        p.competitor_price_gross,
        p.price_gap_net,
        p.price_gap_gross,
        p.price_gap_pct_vs_competitor,
        p.raw_offer_count,
        p.valid_offer_count,
        p.invalid_offer_count,
        p.search_request_count,
        p.generated_at,
        p.competitor_product_url,
        p.sandix_part_number,
        p.competitor_part_number
    FROM reporting.competitor_price_comparison p
    JOIN latest_runs r
      ON r.source_run_id = p.source_run_id
     AND r.competitor_code = p.competitor_code
     AND r.comparison_scope = p.comparison_scope
    ORDER BY p.competitor_code, p.comparison_scope, p.price_gap_pct_vs_competitor DESC NULLS LAST, p.price_gap_gross DESC NULLS LAST, p.product_name
    """,
    """
    CREATE OR REPLACE VIEW reporting.competitor_latest_search_status_v AS
    WITH latest_runs AS (
        SELECT DISTINCT ON (competitor_code, comparison_scope)
            source_run_id,
            competitor_code,
            comparison_scope
        FROM reporting.competitor_batch_kpi
        ORDER BY competitor_code, comparison_scope, generated_at DESC, batch_finished_at DESC NULLS LAST, source_run_id DESC
    )
    SELECT
        s.source_run_id,
        s.competitor_code,
        s.competitor_name,
        s.comparison_scope,
        s.search_status,
        s.request_count,
        s.request_pct,
        s.generated_at
    FROM reporting.competitor_search_status s
    JOIN latest_runs r
      ON r.source_run_id = s.source_run_id
     AND r.competitor_code = s.competitor_code
     AND r.comparison_scope = s.comparison_scope
    ORDER BY s.competitor_code, s.comparison_scope, CASE s.search_status WHEN 'OK' THEN 1 WHEN 'NOT_FOUND' THEN 2 ELSE 3 END
    """,
    """
    CREATE OR REPLACE VIEW reporting.competitor_market_price_comparison_v AS
    WITH latest_runs AS (
        SELECT DISTINCT ON (competitor_code, comparison_scope)
            source_run_id,
            competitor_code,
            comparison_scope
        FROM reporting.competitor_batch_kpi
        ORDER BY competitor_code, comparison_scope, generated_at DESC, batch_finished_at DESC NULLS LAST, source_run_id DESC
    ),
    latest_rows AS (
        SELECT p.*
    FROM reporting.competitor_price_comparison p
    JOIN latest_runs r
      ON r.source_run_id = p.source_run_id
     AND r.competitor_code = p.competitor_code
     AND r.comparison_scope = p.comparison_scope
    )
    SELECT
        comparison_scope,
        product_id,
        sandix_part_number,
        source_identifier,
        searched_identifier,
        product_name,
        MAX(sandix_price_net) AS sandix_price_net,
        MAX(sandix_price_gross) AS sandix_price_gross,
        AVG(competitor_price_net)::numeric(18,4) AS avg_competitor_price_net,
        AVG(competitor_price_gross)::numeric(18,4) AS avg_competitor_price_gross,
        MIN(competitor_price_gross)::numeric(18,4) AS min_competitor_price_gross,
        MAX(competitor_price_gross)::numeric(18,4) AS max_competitor_price_gross,
        COUNT(*)::int AS competitor_count,
        AVG(price_gap_net)::numeric(18,4) AS avg_price_gap_net,
        AVG(price_gap_gross)::numeric(18,4) AS avg_price_gap_gross,
        AVG(price_gap_pct_vs_competitor)::numeric(10,2) AS avg_price_gap_pct_vs_competitor,
        MAX(generated_at) AS generated_at
    FROM latest_rows
    GROUP BY comparison_scope, product_id, sandix_part_number, source_identifier, searched_identifier, product_name
    ORDER BY avg_price_gap_pct_vs_competitor DESC NULLS LAST, avg_price_gap_gross DESC NULLS LAST, product_name
    """,
]
