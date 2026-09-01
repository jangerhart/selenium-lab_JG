from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


COMPETITOR_CODE = "PROFIBAGR"
COMPETITOR_NAME = "Profibagr"
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
    CREATE TABLE IF NOT EXISTS reporting.profibagr_batch_kpi (
        source_run_id uuid PRIMARY KEY,
        competitor_code text NOT NULL,
        competitor_name text NOT NULL,
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
        max_negative_gap_pct_vs_competitor numeric(10,2)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reporting.profibagr_price_comparison (
        source_run_id uuid NOT NULL,
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
        PRIMARY KEY (source_run_id, product_id)
    )
    """,
    """
    ALTER TABLE reporting.profibagr_price_comparison
    ADD COLUMN IF NOT EXISTS profibagr_product_url text
    """,
    """
    CREATE TABLE IF NOT EXISTS reporting.profibagr_search_status (
        source_run_id uuid NOT NULL,
        search_status text NOT NULL,
        request_count integer NOT NULL,
        request_pct numeric(10,2) NOT NULL,
        generated_at timestamptz NOT NULL,
        PRIMARY KEY (source_run_id, search_status)
    )
    """,
    """
    CREATE OR REPLACE VIEW reporting.profibagr_latest_batch_v AS
    SELECT
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
    FROM reporting.profibagr_batch_kpi
    WHERE source_run_id = (
        SELECT source_run_id
        FROM reporting.profibagr_batch_kpi
        ORDER BY generated_at DESC, batch_finished_at DESC NULLS LAST
        LIMIT 1
    )
    """,
    """
    CREATE OR REPLACE VIEW reporting.profibagr_latest_price_comparison_v AS
    SELECT
        source_run_id,
        product_id,
        source_identifier,
        searched_identifier,
        product_name,
        sandix_price_net,
        sandix_price_gross,
        profibagr_price_net,
        profibagr_price_gross,
        price_gap_net,
        price_gap_gross,
        price_gap_pct_vs_competitor,
        raw_offer_count,
        valid_offer_count,
        invalid_offer_count,
        search_request_count,
        generated_at,
        profibagr_product_url
    FROM reporting.profibagr_price_comparison
    WHERE source_run_id = (
        SELECT source_run_id
        FROM reporting.profibagr_batch_kpi
        ORDER BY generated_at DESC, batch_finished_at DESC NULLS LAST
        LIMIT 1
    )
    ORDER BY price_gap_pct_vs_competitor DESC NULLS LAST, price_gap_gross DESC NULLS LAST, product_name
    """,
    """
    CREATE OR REPLACE VIEW reporting.profibagr_latest_overpriced_v AS
    SELECT *
    FROM reporting.profibagr_latest_price_comparison_v
    WHERE price_gap_pct_vs_competitor > 0
    ORDER BY price_gap_pct_vs_competitor DESC NULLS LAST, price_gap_gross DESC NULLS LAST, product_name
    """,
    """
    CREATE OR REPLACE VIEW reporting.profibagr_latest_underpriced_v AS
    SELECT *
    FROM reporting.profibagr_latest_price_comparison_v
    WHERE price_gap_pct_vs_competitor < 0
    ORDER BY price_gap_pct_vs_competitor ASC NULLS LAST, price_gap_gross ASC NULLS LAST, product_name
    """,
    """
    CREATE OR REPLACE VIEW reporting.profibagr_latest_search_status_v AS
    SELECT
        source_run_id,
        search_status,
        request_count,
        request_pct,
        generated_at
    FROM reporting.profibagr_search_status
    WHERE source_run_id = (
        SELECT source_run_id
        FROM reporting.profibagr_batch_kpi
        ORDER BY generated_at DESC, batch_finished_at DESC NULLS LAST
        LIMIT 1
    )
    ORDER BY CASE search_status WHEN 'OK' THEN 1 WHEN 'NOT_FOUND' THEN 2 ELSE 3 END
    """,
]
