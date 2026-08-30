import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
from dotenv import load_dotenv


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


def execute_sql(conn: psycopg.Connection, statements: list[str]) -> None:
    with conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)


def ensure_reporting_tables(conn: psycopg.Connection) -> None:
    execute_sql(
        conn,
        [
            "CREATE SCHEMA IF NOT EXISTS reporting",
            """
            CREATE TABLE IF NOT EXISTS reporting.profibagr_batch_summary (
                analytics_run_id uuid PRIMARY KEY,
                source_run_id uuid NOT NULL,
                competitor_code text NOT NULL,
                competitor_name text NOT NULL,
                generated_at timestamptz NOT NULL,
                batch_started_at timestamptz NOT NULL,
                batch_finished_at timestamptz,
                queue_count integer NOT NULL,
                search_success_count integer NOT NULL,
                not_found_count integer NOT NULL,
                error_count integer NOT NULL,
                offer_count integer NOT NULL,
                matched_product_count integer NOT NULL,
                positive_gap_count integer NOT NULL,
                negative_gap_count integer NOT NULL,
                neutral_gap_count integer NOT NULL,
                max_gap_pct numeric(10,2),
                avg_gap_pct numeric(10,2)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS reporting.profibagr_price_gap (
                analytics_run_id uuid NOT NULL,
                source_run_id uuid NOT NULL,
                product_id bigint NOT NULL,
                source_identifier text,
                searched_identifier text NOT NULL,
                product_name text,
                own_selling_price_net numeric(18,4),
                own_selling_price_gross numeric(18,4),
                best_competitor_price_without_vat numeric(18,4),
                best_competitor_price_with_vat numeric(18,4),
                price_gap_net numeric(18,4),
                price_gap_gross numeric(18,4),
                price_gap_pct numeric(10,2),
                offer_count integer NOT NULL,
                search_request_count integer NOT NULL,
                generated_at timestamptz NOT NULL,
                PRIMARY KEY (analytics_run_id, product_id),
                CONSTRAINT fk_profibagr_price_gap_summary
                    FOREIGN KEY (analytics_run_id) REFERENCES reporting.profibagr_batch_summary(analytics_run_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_profibagr_price_gap_run_gap
            ON reporting.profibagr_price_gap (analytics_run_id, price_gap_pct DESC NULLS LAST, price_gap_gross DESC NULLS LAST)
            """,
            """
            CREATE OR REPLACE VIEW reporting.profibagr_price_gap_v AS
            SELECT
                analytics_run_id,
                source_run_id,
                product_id,
                source_identifier,
                searched_identifier,
                product_name,
                own_selling_price_net,
                own_selling_price_gross,
                best_competitor_price_without_vat,
                best_competitor_price_with_vat,
                price_gap_net,
                price_gap_gross,
                price_gap_pct,
                offer_count,
                search_request_count,
                generated_at
            FROM reporting.profibagr_price_gap
            ORDER BY price_gap_pct DESC NULLS LAST, price_gap_gross DESC NULLS LAST
            """,
        ],
    )


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
                queue_count,
                search_success_count,
                not_found_count,
                error_count,
                offer_count
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


def fetch_gap_rows(conn: psycopg.Connection, source_run_id: uuid.UUID) -> list[dict[str, object]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH matched AS (
                SELECT
                    sr.run_id,
                    sr.search_request_id,
                    sr.searched_identifier,
                    sp.product_id,
                    sp.source_identifier,
                    cp.product_name,
                    cp.selling_price_net AS own_selling_price_net,
                    cp.selling_price_gross AS own_selling_price_gross,
                    MIN(oo.price_without_vat) AS best_competitor_price_without_vat,
                    MIN(oo.price_with_vat) AS best_competitor_price_with_vat,
                    COUNT(DISTINCT oo.observation_id) AS offer_count
                FROM scraper.search_request sr
                JOIN scraper.search_request_product sp
                  ON sp.search_request_id = sr.search_request_id
                JOIN core.product_current_v cp
                  ON cp.product_id = sp.product_id
                JOIN scraper.offer_observation oo
                  ON oo.search_request_id = sr.search_request_id
                WHERE sr.run_id = %s
                  AND sr.status = 'OK'
                  AND oo.price_with_vat IS NOT NULL
                GROUP BY
                    sr.run_id,
                    sr.search_request_id,
                    sr.searched_identifier,
                    sp.product_id,
                    sp.source_identifier,
                    cp.product_name,
                    cp.selling_price_net,
                    cp.selling_price_gross
            )
            SELECT
                run_id,
                product_id,
                source_identifier,
                searched_identifier,
                product_name,
                own_selling_price_net,
                own_selling_price_gross,
                best_competitor_price_without_vat,
                best_competitor_price_with_vat,
                CASE
                    WHEN own_selling_price_net IS NULL OR best_competitor_price_without_vat IS NULL THEN NULL
                    ELSE round(own_selling_price_net - best_competitor_price_without_vat, 4)
                END AS price_gap_net,
                CASE
                    WHEN own_selling_price_gross IS NULL OR best_competitor_price_with_vat IS NULL THEN NULL
                    ELSE round(own_selling_price_gross - best_competitor_price_with_vat, 4)
                END AS price_gap_gross,
                CASE
                    WHEN own_selling_price_gross IS NULL OR own_selling_price_gross = 0 OR best_competitor_price_with_vat IS NULL THEN NULL
                    ELSE round(((own_selling_price_gross - best_competitor_price_with_vat) / own_selling_price_gross) * 100, 2)
                END AS price_gap_pct,
                offer_count,
                1 AS search_request_count
            FROM matched
            ORDER BY price_gap_pct DESC NULLS LAST, price_gap_gross DESC NULLS LAST
            """,
            (source_run_id,),
        )
        columns = [desc.name for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def write_snapshot(
    conn: psycopg.Connection,
    analytics_run_id: uuid.UUID,
    source_run: dict[str, object],
    gap_rows: list[dict[str, object]],
) -> None:
    positive_gap_count = sum(1 for row in gap_rows if row["price_gap_pct"] is not None and row["price_gap_pct"] > 0)
    negative_gap_count = sum(1 for row in gap_rows if row["price_gap_pct"] is not None and row["price_gap_pct"] < 0)
    neutral_gap_count = sum(1 for row in gap_rows if row["price_gap_pct"] == 0)
    gap_values = [row["price_gap_pct"] for row in gap_rows if row["price_gap_pct"] is not None]
    max_gap_pct = max(gap_values) if gap_values else None
    avg_gap_pct = (sum(gap_values) / len(gap_values)) if gap_values else None

    with conn.cursor() as cur:
        cur.execute("DELETE FROM reporting.profibagr_price_gap WHERE source_run_id = %s", (source_run["run_id"],))
        cur.execute("DELETE FROM reporting.profibagr_batch_summary WHERE source_run_id = %s", (source_run["run_id"],))
        cur.execute(
            """
            INSERT INTO reporting.profibagr_batch_summary (
                analytics_run_id,
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
                offer_count,
                matched_product_count,
                positive_gap_count,
                negative_gap_count,
                neutral_gap_count,
                max_gap_pct,
                avg_gap_pct
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                analytics_run_id,
                source_run["run_id"],
                source_run["competitor_code"],
                source_run["competitor_name"],
                datetime.now(timezone.utc),
                source_run["started_at"],
                source_run["finished_at"],
                source_run["queue_count"],
                source_run["search_success_count"],
                source_run["not_found_count"],
                source_run["error_count"],
                source_run["offer_count"],
                len(gap_rows),
                positive_gap_count,
                negative_gap_count,
                neutral_gap_count,
                max_gap_pct,
                avg_gap_pct,
            ),
        )
        cur.executemany(
            """
            INSERT INTO reporting.profibagr_price_gap (
                analytics_run_id,
                source_run_id,
                product_id,
                source_identifier,
                searched_identifier,
                product_name,
                own_selling_price_net,
                own_selling_price_gross,
                best_competitor_price_without_vat,
                best_competitor_price_with_vat,
                price_gap_net,
                price_gap_gross,
                price_gap_pct,
                offer_count,
                search_request_count,
                generated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            [
                (
                    analytics_run_id,
                    source_run["run_id"],
                    row["product_id"],
                    row["source_identifier"],
                    row["searched_identifier"],
                    row["product_name"],
                    row["own_selling_price_net"],
                    row["own_selling_price_gross"],
                    row["best_competitor_price_without_vat"],
                    row["best_competitor_price_with_vat"],
                    row["price_gap_net"],
                    row["price_gap_gross"],
                    row["price_gap_pct"],
                    row["offer_count"],
                    row["search_request_count"],
                    datetime.now(timezone.utc),
                )
                for row in gap_rows
            ],
        )


def print_preview(source_run: dict[str, object], gap_rows: list[dict[str, object]]) -> None:
    print(
        f"Latest Profibagr run {source_run['run_id']} produced {len(gap_rows)} matched products from {source_run['search_success_count']} successful search requests"
    )
    print("Top price gaps:")
    for row in gap_rows[:10]:
        print(
            f"- {row['searched_identifier']}: own {row['own_selling_price_gross']} vs competitor {row['best_competitor_price_with_vat']} => gap {row['price_gap_gross']} ({row['price_gap_pct']}%)"
        )


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / "profibagr-scraper" / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env")

    analytics_run_id = uuid.uuid4()
    try:
        with connect(get_env_default("PG_MONITOR_DB", "sandix_price_monitor"), "PG_MONITOR") as monitor_conn, connect(
            get_env_default("PG_ANALYTICS_DB", "sandix_price_analytics"), "PG_ANALYTICS"
        ) as analytics_conn:
            ensure_reporting_tables(analytics_conn)
            source_run = fetch_latest_run(monitor_conn)
            gap_rows = fetch_gap_rows(monitor_conn, source_run["run_id"])
            write_snapshot(analytics_conn, analytics_run_id, source_run, gap_rows)
            analytics_conn.commit()
            print_preview(source_run, gap_rows)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Analytics build failed: {exc}", file=sys.stderr)
        return 1

    print(f"Analytics snapshot stored as {analytics_run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
