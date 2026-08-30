import argparse
import csv
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytds
import psycopg
from dotenv import load_dotenv


CSV_HEADERS = [
    "sync_run_id",
    "extracted_at",
    "source_server",
    "source_database",
    "source_row_id",
    "ids",
    "product_name",
    "stock_quantity",
    "available_quantity",
    "web_enabled",
    "purchase_price_net",
    "purchase_price_gross",
    "purchase_currency",
    "selling_price_net",
    "selling_price_gross",
    "selling_currency",
    "source_saved_at",
]


def setup_logging(run_id: str, logs_dir: Path) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"pohoda_{run_id}.log"

    logger = logging.getLogger("pohoda_etl")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logger.info("START")
    logger.info("LOG FILE %s", log_path)
    return logger


def get_env_or_raise(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_env_fallback(name: str, fallback: str | None = None) -> str:
    value = os.getenv(name)
    if value:
        return value
    if fallback is not None:
        return fallback
    raise RuntimeError(f"Missing required environment variable: {name}")


def decimal_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def bool_to_str(value: Any) -> str:
    if value is None:
        return ""
    return "true" if bool(value) else "false"


def datetime_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat()
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def connect_monitor_db() -> psycopg.Connection:
    host = os.getenv("PG_MONITOR_HOST") or get_env_or_raise("PG_PROVISION_HOST")
    port = int(os.getenv("PG_MONITOR_PORT") or get_env_or_raise("PG_PROVISION_PORT"))
    dbname = get_env_fallback("PG_MONITOR_DB", "sandix_price_monitor")
    user = os.getenv("PG_MONITOR_USER") or get_env_or_raise("PG_PROVISION_USER")
    password = os.getenv("PG_MONITOR_PASSWORD") or get_env_or_raise("PG_PROVISION_PASSWORD")
    sslmode = os.getenv("PG_MONITOR_SSLMODE") or os.getenv("PG_PROVISION_SSLMODE")

    conn_kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "dbname": dbname,
        "user": user,
        "password": password,
    }
    if sslmode:
        conn_kwargs["sslmode"] = sslmode
    return psycopg.connect(**conn_kwargs)


def source_price_tuple(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("NakupC"),
        row.get("NakupDPH"),
        row.get("CMKodNC"),
        row.get("ProdejKc"),
        row.get("ProdejDPH"),
        row.get("CMKodPC"),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="POHODA read-only ETL snapshot extractor")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional row limit for smoke tests.",
    )
    return parser.parse_args()


def build_query(limit: int | None) -> str:
    top_clause = f"TOP ({limit}) " if limit is not None else ""
    return f"""
        SELECT {top_clause}
            ID,
            IDS,
            Nazev,
            StavZ,
            VPrDispMnoz,
            IObchod,
            NakupC,
            NakupDPH,
            ProdejKc,
            ProdejDPH,
            CMKodNC,
            CMKodPC,
            DatSave
        FROM dbo.SKz
        ORDER BY ID
    """


def fetch_rows(conn, limit: int | None) -> list[dict[str, Any]]:
    query = build_query(limit)
    cur = conn.cursor()
    cur.execute(query)
    columns = [desc[0] for desc in cur.description]
    rows: list[dict[str, Any]] = []
    for raw_row in cur.fetchall():
        rows.append(dict(zip(columns, raw_row, strict=False)))
    return rows


def map_row(row: dict[str, Any], run_id: str, extracted_at: str, source_server: str, source_database: str) -> dict[str, Any]:
    return {
        "sync_run_id": run_id,
        "extracted_at": extracted_at,
        "source_server": source_server,
        "source_database": source_database,
        "source_row_id": row.get("ID", ""),
        "ids": row.get("IDS", ""),
        "product_name": row.get("Nazev", ""),
        "stock_quantity": decimal_to_str(row.get("StavZ")),
        "available_quantity": decimal_to_str(row.get("VPrDispMnoz")),
        "web_enabled": bool_to_str(row.get("IObchod")),
        "purchase_price_net": decimal_to_str(row.get("NakupC")),
        "purchase_price_gross": decimal_to_str(row.get("NakupDPH")),
        "purchase_currency": row.get("CMKodNC", "") or "",
        "selling_price_net": decimal_to_str(row.get("ProdejKc")),
        "selling_price_gross": decimal_to_str(row.get("ProdejDPH")),
        "selling_currency": row.get("CMKodPC", "") or "",
        "source_saved_at": datetime_to_str(row.get("DatSave")),
    }


def write_csv(output_path: Path, rows: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_HEADERS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def load_into_monitor_db(
    conn: psycopg.Connection,
    source_rows: list[dict[str, Any]],
    source_server: str,
    source_database: str,
    sync_run_id: uuid.UUID,
    extracted_at: datetime,
) -> dict[str, int]:
    source_ids = [int(row["ID"]) for row in source_rows]
    source_id_set = set(source_ids)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT pohoda_id
            FROM source_pohoda.stock_current
            WHERE source_database = %s
              AND pohoda_id = ANY(%s)
            """,
            (source_database, source_ids),
        )
        existing_source_ids = {int(row[0]) for row in cur.fetchall()}

        stock_rows = [
            (
                source_database,
                int(row["ID"]),
                row.get("IDS"),
                row.get("Nazev"),
                row.get("StavZ"),
                row.get("VPrDispMnoz"),
                row.get("IObchod"),
                row.get("NakupC"),
                row.get("NakupDPH"),
                row.get("CMKodNC"),
                row.get("ProdejKc"),
                row.get("ProdejDPH"),
                row.get("CMKodPC"),
                row.get("DatSave"),
                extracted_at,
                sync_run_id,
            )
            for row in source_rows
        ]

        cur.executemany(
            """
            INSERT INTO source_pohoda.stock_current (
                source_database,
                pohoda_id,
                ids,
                product_name,
                stock_quantity,
                available_quantity,
                web_enabled,
                purchase_price_net,
                purchase_price_gross,
                purchase_currency,
                selling_price_net,
                selling_price_gross,
                selling_currency,
                source_saved_at,
                extracted_at,
                last_sync_run_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (source_database, pohoda_id) DO UPDATE SET
                ids = EXCLUDED.ids,
                product_name = EXCLUDED.product_name,
                stock_quantity = EXCLUDED.stock_quantity,
                available_quantity = EXCLUDED.available_quantity,
                web_enabled = EXCLUDED.web_enabled,
                purchase_price_net = EXCLUDED.purchase_price_net,
                purchase_price_gross = EXCLUDED.purchase_price_gross,
                purchase_currency = EXCLUDED.purchase_currency,
                selling_price_net = EXCLUDED.selling_price_net,
                selling_price_gross = EXCLUDED.selling_price_gross,
                selling_currency = EXCLUDED.selling_currency,
                source_saved_at = EXCLUDED.source_saved_at,
                extracted_at = EXCLUDED.extracted_at,
                last_sync_run_id = EXCLUDED.last_sync_run_id
            """,
            stock_rows,
        )

        product_rows = [(source_database, int(row["ID"])) for row in source_rows]
        cur.executemany(
            """
            INSERT INTO core.product (source_database, pohoda_id)
            VALUES (%s, %s)
            ON CONFLICT (source_database, pohoda_id) DO UPDATE SET
                retired_at = NULL
            """,
            product_rows,
        )

        cur.execute(
            """
            SELECT product_id, pohoda_id
            FROM core.product
            WHERE source_database = %s
              AND pohoda_id = ANY(%s)
            """,
            (source_database, source_ids),
        )
        product_id_by_pohoda_id = {int(pohoda_id): int(product_id) for product_id, pohoda_id in cur.fetchall()}

        cur.execute(
            """
            SELECT DISTINCT ON (product_id)
                product_id,
                purchase_price_net,
                purchase_price_gross,
                purchase_currency,
                selling_price_net,
                selling_price_gross,
                selling_currency
            FROM core.own_price_history
            WHERE product_id = ANY(%s)
            ORDER BY product_id, valid_from DESC, own_price_history_id DESC
            """,
            (list(product_id_by_pohoda_id.values()),),
        )
        latest_history_by_product = {
            int(product_id): (
                purchase_price_net,
                purchase_price_gross,
                purchase_currency,
                selling_price_net,
                selling_price_gross,
                selling_currency,
            )
            for product_id, purchase_price_net, purchase_price_gross, purchase_currency, selling_price_net, selling_price_gross, selling_currency in cur.fetchall()
        }

        own_price_rows = []
        for row in source_rows:
            product_id = product_id_by_pohoda_id[int(row["ID"])]
            current_tuple = source_price_tuple(row)
            latest_tuple = latest_history_by_product.get(product_id)
            if latest_tuple == current_tuple:
                continue
            own_price_rows.append(
                (
                    product_id,
                    extracted_at,
                    row.get("NakupC"),
                    row.get("NakupDPH"),
                    row.get("CMKodNC"),
                    row.get("ProdejKc"),
                    row.get("ProdejDPH"),
                    row.get("CMKodPC"),
                    sync_run_id,
                )
            )

        if own_price_rows:
            cur.executemany(
                """
                INSERT INTO core.own_price_history (
                    product_id,
                    valid_from,
                    purchase_price_net,
                    purchase_price_gross,
                    purchase_currency,
                    selling_price_net,
                    selling_price_gross,
                    selling_currency,
                    sync_run_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                own_price_rows,
            )

        cur.execute(
            """
            UPDATE etl.pohoda_sync_run
            SET finished_at = %s,
                status = 'SUCCESS',
                rows_read = %s,
                rows_inserted = %s,
                rows_updated = %s,
                price_changes = %s,
                error_count = 0,
                error_message = NULL
            WHERE sync_run_id = %s
            """,
            (
                extracted_at,
                len(source_rows),
                len(source_id_set - existing_source_ids),
                len(source_id_set & existing_source_ids),
                len(own_price_rows),
                sync_run_id,
            ),
        )

    return {
        "rows_read": len(source_rows),
        "rows_inserted": len(source_id_set - existing_source_ids),
        "rows_updated": len(source_id_set & existing_source_ids),
        "price_changes": len(own_price_rows),
    }


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / "profibagr-scraper" / ".env")
    load_dotenv()
    args = parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = Path(__file__).resolve().parent
    logs_dir = base_dir / "logs"
    data_dir = base_dir / "data" / "raw" / "pohoda"
    csv_path = data_dir / f"pohoda_{run_id}.csv"

    logger = setup_logging(run_id, logs_dir)

    host = get_env_or_raise("POHODA_DB_HOST")
    port = int(get_env_or_raise("POHODA_DB_PORT"))
    database = get_env_or_raise("POHODA_DB_NAME")
    user = get_env_or_raise("POHODA_DB_USER")
    password = get_env_or_raise("POHODA_DB_PASSWORD")

    logger.info("CONNECTING: %s:%s/%s", host, port, database)

    try:
        conn = pytds.connect(
            server=host,
            port=port,
            database=database,
            user=user,
            password=password,
            login_timeout=15,
            timeout=15,
            readonly=True,
            autocommit=True,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("DATABASE ERROR")
        logger.error("END")
        print(f"Database error: {exc}")
        return 1

    try:
        with conn:
            source_rows = fetch_rows(conn, args.limit)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("FETCH ERROR")
        logger.error("END")
        print(f"Fetch error: {exc}")
        return 1

    extracted_at_dt = datetime.now(timezone.utc)
    sync_run_id = uuid.uuid4()
    extracted_at = extracted_at_dt.isoformat()
    mapped_rows = [
        map_row(
            row,
            run_id=str(sync_run_id),
            extracted_at=extracted_at,
            source_server=host,
            source_database=database,
        )
        for row in source_rows
    ]

    write_csv(csv_path, mapped_rows)
    try:
        monitor_conn = connect_monitor_db()
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("MONITOR CONNECTION ERROR")
        logger.error("END")
        print(f"Monitor database error: {exc}")
        return 1

    try:
        with monitor_conn:
            with monitor_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO etl.pohoda_sync_run (
                        sync_run_id,
                        started_at,
                        status,
                        source_server,
                        source_database,
                        rows_read,
                        rows_inserted,
                        rows_updated,
                        price_changes,
                        error_count,
                        error_message
                    ) VALUES (%s, %s, 'RUNNING', %s, %s, 0, 0, 0, 0, 0, NULL)
                    """,
                    (
                        sync_run_id,
                        extracted_at_dt,
                        host,
                        database,
                    ),
                )
            monitor_conn.commit()
            with monitor_conn.transaction():
                stats = load_into_monitor_db(
                    monitor_conn,
                    source_rows,
                    source_server=host,
                    source_database=database,
                    sync_run_id=sync_run_id,
                    extracted_at=extracted_at_dt,
                )
    except Exception as exc:  # pylint: disable=broad-except
        try:
            with monitor_conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE etl.pohoda_sync_run
                    SET finished_at = %s,
                        status = 'FAILED',
                        error_count = 1,
                        error_message = %s
                    WHERE sync_run_id = %s
                    """,
                    (extracted_at_dt, str(exc), sync_run_id),
                )
            monitor_conn.commit()
        except Exception:  # pylint: disable=broad-except
            monitor_conn.rollback()
        logger.exception("MONITOR LOAD ERROR")
        logger.error("END")
        print(f"Monitor load error: {exc}")
        return 1

    logger.info("ROWS: %s", len(mapped_rows))
    logger.info("MONITOR STATS: %s", stats)
    logger.info("CSV CREATED: %s", csv_path)
    logger.info("END")

    print(csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
