import os
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


def connect(dbname: str) -> psycopg.Connection:
    conn_kwargs: dict[str, object] = {
        "host": get_env("PG_PROVISION_HOST"),
        "port": int(get_env("PG_PROVISION_PORT")),
        "dbname": dbname,
        "user": get_env("PG_PROVISION_USER"),
        "password": get_env("PG_PROVISION_PASSWORD"),
    }
    sslmode = os.getenv("PG_PROVISION_SSLMODE")
    if sslmode:
        conn_kwargs["sslmode"] = sslmode
    return psycopg.connect(**conn_kwargs)


MONITOR_DDL = [
    "CREATE SCHEMA IF NOT EXISTS source_pohoda",
    "CREATE SCHEMA IF NOT EXISTS core",
    "CREATE SCHEMA IF NOT EXISTS etl",
    "CREATE SCHEMA IF NOT EXISTS scraper",
    "CREATE SCHEMA IF NOT EXISTS export",
    "CREATE SCHEMA IF NOT EXISTS legacy",
    """
    CREATE TABLE IF NOT EXISTS etl.pohoda_sync_run (
        sync_run_id uuid PRIMARY KEY,
        started_at timestamptz NOT NULL,
        finished_at timestamptz,
        status text NOT NULL,
        source_server text,
        source_database text,
        rows_read integer,
        rows_inserted integer,
        rows_updated integer,
        price_changes integer,
        error_count integer,
        error_message text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_pohoda.stock_current (
        source_database text NOT NULL,
        pohoda_id bigint NOT NULL,
        ids text,
        product_name text,
        stock_quantity numeric(18,6),
        available_quantity numeric(18,6),
        web_enabled boolean,
        purchase_price_net numeric(18,4),
        purchase_price_gross numeric(18,4),
        purchase_currency char(3),
        selling_price_net numeric(18,4),
        selling_price_gross numeric(18,4),
        selling_currency char(3),
        source_saved_at timestamp,
        extracted_at timestamptz NOT NULL,
        last_sync_run_id uuid NOT NULL,
        PRIMARY KEY (source_database, pohoda_id),
        CONSTRAINT fk_stock_current_sync_run
            FOREIGN KEY (last_sync_run_id) REFERENCES etl.pohoda_sync_run(sync_run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.product (
        product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        source_database text NOT NULL,
        pohoda_id bigint NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        retired_at timestamptz,
        UNIQUE (source_database, pohoda_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.own_price_history (
        own_price_history_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        product_id bigint NOT NULL,
        valid_from timestamptz NOT NULL,
        purchase_price_net numeric(18,4),
        purchase_price_gross numeric(18,4),
        purchase_currency char(3),
        selling_price_net numeric(18,4),
        selling_price_gross numeric(18,4),
        selling_currency char(3),
        sync_run_id uuid NOT NULL,
        CONSTRAINT fk_own_price_product
            FOREIGN KEY (product_id) REFERENCES core.product(product_id),
        CONSTRAINT fk_own_price_sync_run
            FOREIGN KEY (sync_run_id) REFERENCES etl.pohoda_sync_run(sync_run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS core.product_identifier (
        product_identifier_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        product_id bigint NOT NULL,
        identifier text NOT NULL,
        identifier_normalized text NOT NULL,
        identifier_type text NOT NULL,
        manufacturer text,
        is_primary boolean NOT NULL DEFAULT false,
        valid_from timestamptz,
        valid_to timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT fk_product_identifier_product
            FOREIGN KEY (product_id) REFERENCES core.product(product_id),
        CONSTRAINT uq_product_identifier UNIQUE (product_id, identifier_normalized, identifier_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scraper.competitor (
        competitor_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        competitor_code text NOT NULL UNIQUE,
        competitor_name text NOT NULL,
        base_url text,
        default_currency char(3),
        enabled boolean NOT NULL DEFAULT true,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scraper.scrape_run (
        run_id uuid PRIMARY KEY,
        competitor_id bigint NOT NULL,
        started_at timestamptz NOT NULL,
        finished_at timestamptz,
        status text NOT NULL,
        queue_count integer,
        search_success_count integer,
        not_found_count integer,
        error_count integer,
        offer_count integer,
        raw_file_path text,
        raw_file_sha256 text,
        scraper_version text,
        error_message text,
        CONSTRAINT fk_scrape_run_competitor
            FOREIGN KEY (competitor_id) REFERENCES scraper.competitor(competitor_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scraper.search_request (
        search_request_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        run_id uuid NOT NULL,
        searched_identifier text NOT NULL,
        searched_identifier_norm text,
        requested_at timestamptz NOT NULL DEFAULT now(),
        completed_at timestamptz,
        status text NOT NULL,
        match_count integer,
        http_status integer,
        error_type text,
        error_message text,
        CONSTRAINT fk_search_request_run
            FOREIGN KEY (run_id) REFERENCES scraper.scrape_run(run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scraper.search_request_product (
        search_request_id bigint NOT NULL,
        product_id bigint NOT NULL,
        source_identifier text,
        PRIMARY KEY (search_request_id, product_id),
        CONSTRAINT fk_search_request_product_request
            FOREIGN KEY (search_request_id) REFERENCES scraper.search_request(search_request_id),
        CONSTRAINT fk_search_request_product_product
            FOREIGN KEY (product_id) REFERENCES core.product(product_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scraper.offer_observation (
        observation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        search_request_id bigint NOT NULL,
        found_identifier text,
        found_identifier_norm text,
        competitor_product_name text,
        price_without_vat numeric(18,4),
        price_with_vat numeric(18,4),
        currency char(3),
        availability_raw text,
        product_url text,
        observed_at timestamptz NOT NULL DEFAULT now(),
        match_type text,
        match_confidence numeric(5,4),
        CONSTRAINT fk_offer_observation_request
            FOREIGN KEY (search_request_id) REFERENCES scraper.search_request(search_request_id)
    )
    """,
    """
    CREATE OR REPLACE VIEW core.product_current_v AS
    SELECT
        p.product_id,
        p.source_database,
        p.pohoda_id,
        s.ids,
        s.product_name,
        s.stock_quantity,
        s.available_quantity,
        s.web_enabled,
        s.purchase_price_net,
        s.purchase_price_gross,
        s.purchase_currency,
        s.selling_price_net,
        s.selling_price_gross,
        s.selling_currency,
        s.source_saved_at
    FROM core.product p
    JOIN source_pohoda.stock_current s
      ON s.source_database = p.source_database
     AND s.pohoda_id = p.pohoda_id
    """,
    """
    CREATE OR REPLACE VIEW core.product_search_identifier_v AS
    SELECT
        product_id,
        ids AS source_identifier,
        btrim(upper(ids)) AS search_identifier,
        regexp_replace(btrim(upper(ids)), '[\\s\\-/]', '', 'g') AS search_identifier_normalized,
        'CURRENT_IDS'::text AS transformation_type
    FROM core.product_current_v
    WHERE ids IS NOT NULL AND btrim(ids) <> ''
    """,
    """
    CREATE OR REPLACE VIEW scraper.v_search_queue AS
    SELECT DISTINCT ON (search_identifier_normalized)
        psi.product_id,
        psi.source_identifier,
        psi.search_identifier,
        psi.search_identifier_normalized
    FROM core.product_search_identifier_v psi
    JOIN core.product_current_v c
      ON c.product_id = psi.product_id
    WHERE COALESCE(c.web_enabled, false) = true
      AND COALESCE(c.available_quantity, 0) > 0
    ORDER BY psi.search_identifier_normalized, psi.product_id
    """,
    """
    CREATE OR REPLACE VIEW export.product_current_v AS
    SELECT * FROM core.product_current_v
    """,
    """
    CREATE OR REPLACE VIEW export.own_price_history_v AS
    SELECT
        oph.own_price_history_id,
        oph.product_id,
        p.source_database,
        p.pohoda_id,
        oph.valid_from,
        oph.purchase_price_net,
        oph.purchase_price_gross,
        oph.purchase_currency,
        oph.selling_price_net,
        oph.selling_price_gross,
        oph.selling_currency,
        oph.sync_run_id
    FROM core.own_price_history oph
    JOIN core.product p ON p.product_id = oph.product_id
    """,
    """
    CREATE OR REPLACE VIEW export.competitor_offer_history_v AS
    SELECT
        oo.observation_id,
        oo.search_request_id,
        sr.run_id,
        sr.searched_identifier,
        sr.searched_identifier_norm,
        oo.found_identifier,
        oo.found_identifier_norm,
        oo.competitor_product_name,
        oo.price_without_vat,
        oo.price_with_vat,
        oo.currency,
        oo.availability_raw,
        oo.product_url,
        oo.observed_at,
        oo.match_type,
        oo.match_confidence
    FROM scraper.offer_observation oo
    JOIN scraper.search_request sr ON sr.search_request_id = oo.search_request_id
    """,
    """
    CREATE OR REPLACE VIEW export.scrape_run_v AS
    SELECT
        sr.run_id,
        sr.competitor_id,
        c.competitor_code,
        c.competitor_name,
        sr.started_at,
        sr.finished_at,
        sr.status,
        sr.queue_count,
        sr.search_success_count,
        sr.not_found_count,
        sr.error_count,
        sr.offer_count,
        sr.raw_file_path,
        sr.raw_file_sha256,
        sr.scraper_version,
        sr.error_message
    FROM scraper.scrape_run sr
    JOIN scraper.competitor c ON c.competitor_id = sr.competitor_id
    """,
]


ANALYTICS_DDL = [
    "CREATE SCHEMA IF NOT EXISTS mart",
    "CREATE SCHEMA IF NOT EXISTS dim",
    "CREATE SCHEMA IF NOT EXISTS fact",
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
]


def execute_sql(conn: psycopg.Connection, statements: list[str]) -> None:
    with conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / 'profibagr-scraper' / '.env')
    load_dotenv()

    with connect(get_env_default('PG_MONITOR_DB', 'sandix_price_monitor')) as conn:
        execute_sql(conn, MONITOR_DDL)
        conn.commit()

    with connect(get_env_default('PG_ANALYTICS_DB', 'sandix_price_analytics')) as conn:
        execute_sql(conn, ANALYTICS_DDL)
        conn.commit()

    print('Bootstrap completed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
