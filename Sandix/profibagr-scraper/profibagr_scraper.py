import argparse
import csv
import json
import logging
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import signal
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
import psycopg
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from sandix.alternatives import fetch_variant_suffixes  # noqa: E402
from sandix.part_numbers import dedupe_part_numbers_by_base  # noqa: E402


BASE_URL = "https://www.profibagr.cz"
SEARCH_PATH = "/search"
REQUEST_TIMEOUT_SECONDS = 15
REQUEST_DELAY_SECONDS_DEFAULT = 3.0
REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=10.0)
STALE_RUN_ABORT_MINUTES = 30
DB_QUERY = """
SELECT search_identifier
FROM scraper.v_search_queue
ORDER BY search_identifier_normalized, search_identifier
LIMIT 500;
"""

CSV_HEADERS = [
    "run_id",
    "scraped_at",
    "search_part_number",
    "status",
    "match_count",
    "found_part_number",
    "product_name",
    "price_without_vat",
    "price_with_vat",
    "currency",
    "availability_raw",
    "product_url",
    "http_status",
    "error_type",
    "error_message",
]


@dataclass
class FetchResult:
    status: str
    match_count: int
    rows: list[dict[str, Any]]


def normalize_part_number(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().upper()


def normalize_part_number_loose(value: str | None) -> str:
    normalized = normalize_part_number(value)
    return re.sub(r"[\s-]", "", normalized)


def setup_logging(run_id: str, logs_dir: Path) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"profibagr_{run_id}.log"

    logger = logging.getLogger("profibagr_scraper")
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


def get_request_delay_seconds() -> float:
    raw_value = os.getenv("REQUEST_DELAY_SECONDS")
    if not raw_value:
        return REQUEST_DELAY_SECONDS_DEFAULT
    try:
        return max(float(raw_value), 0.0)
    except ValueError as exc:
        raise RuntimeError("REQUEST_DELAY_SECONDS must be a number") from exc


def connect_monitor_db() -> psycopg.Connection:
    conninfo = {
        "host": os.getenv("PG_MONITOR_HOST") or get_env_or_raise("PG_PROVISION_HOST"),
        "port": int(os.getenv("PG_MONITOR_PORT") or get_env_or_raise("PG_PROVISION_PORT")),
        "dbname": os.getenv("PG_MONITOR_DB") or "sandix_price_monitor",
        "user": os.getenv("PG_MONITOR_USER") or get_env_or_raise("PG_PROVISION_USER"),
        "password": os.getenv("PG_MONITOR_PASSWORD") or get_env_or_raise("PG_PROVISION_PASSWORD"),
    }
    sslmode = os.getenv("PG_MONITOR_SSLMODE") or os.getenv("PG_PROVISION_SSLMODE")
    if sslmode:
        conninfo["sslmode"] = sslmode
    return psycopg.connect(**conninfo, autocommit=True)


def connect_analytics_db() -> psycopg.Connection:
    conninfo = {
        "host": os.getenv("PG_ANALYTICS_HOST") or get_env_or_raise("PG_PROVISION_HOST"),
        "port": int(os.getenv("PG_ANALYTICS_PORT") or get_env_or_raise("PG_PROVISION_PORT")),
        "dbname": os.getenv("PG_ANALYTICS_DB") or "sandix_price_analytics",
        "user": os.getenv("PG_ANALYTICS_USER") or get_env_or_raise("PG_PROVISION_USER"),
        "password": os.getenv("PG_ANALYTICS_PASSWORD") or get_env_or_raise("PG_PROVISION_PASSWORD"),
    }
    sslmode = os.getenv("PG_ANALYTICS_SSLMODE") or os.getenv("PG_PROVISION_SSLMODE")
    if sslmode:
        conninfo["sslmode"] = sslmode
    return psycopg.connect(**conninfo, autocommit=True)


def parse_price_decimal(raw_value: str | None) -> Decimal | None:
    if not raw_value:
        return None

    cleaned = raw_value.replace("\xa0", " ").strip()
    cleaned = cleaned.replace("Kč", "")
    cleaned = cleaned.replace("s DPH", "")
    cleaned = cleaned.replace("bez DPH", "")
    cleaned = cleaned.replace(" ", "")
    cleaned = cleaned.replace(",", ".")
    cleaned = re.sub(r"[^0-9.]", "", cleaned)

    if not cleaned:
        return None

    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def decimal_to_str(value: Decimal | None) -> str:
    return f"{value:.2f}" if value is not None else ""


def parse_upgates_json(html: str) -> dict[str, Any] | None:
    match = re.search(r"var upgates = (\{.*?\});upgates\.callEvents=", html, re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def fetch_part_numbers_from_db(logger: logging.Logger) -> list[str]:
    with connect_monitor_db() as conn:
        with conn.cursor() as cur:
            cur.execute(DB_QUERY)
            rows = cur.fetchall()

    with connect_analytics_db() as conn:
        suffixes = fetch_variant_suffixes(conn)

    logger.info("DATABASE CONNECTED")

    queue_values = [normalize_part_number(str(row[0])) for row in rows]
    return dedupe_part_numbers_by_base(queue_values, suffixes)[:500]


def ensure_competitor_id(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO scraper.competitor (competitor_code, competitor_name, base_url, default_currency, enabled)
            VALUES ('PROFIBAGR', 'Profibagr', 'https://www.profibagr.cz', 'CZK', true)
            ON CONFLICT (competitor_code) DO UPDATE SET
                competitor_name = EXCLUDED.competitor_name,
                base_url = EXCLUDED.base_url,
                default_currency = EXCLUDED.default_currency,
                enabled = EXCLUDED.enabled
            RETURNING competitor_id
            """
        )
        return int(cur.fetchone()[0])


def resolve_products_for_search_identifier(conn: psycopg.Connection, search_identifier: str) -> list[dict[str, Any]]:
    normalized = normalize_part_number_loose(search_identifier)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT
                psi.product_id,
                psi.source_identifier,
                psi.search_identifier,
                psi.search_identifier_normalized
            FROM core.product_search_identifier_v psi
            JOIN core.product_current_v c ON c.product_id = psi.product_id
            WHERE c.web_enabled = true
              AND c.available_quantity > 0
              AND psi.search_identifier_normalized = %s
            ORDER BY psi.product_id, psi.source_identifier
            """,
            (normalized,),
        )
        rows = cur.fetchall()
    return [
        {
            "product_id": int(product_id),
            "source_identifier": source_identifier,
            "search_identifier": search_identifier_value,
            "search_identifier_normalized": search_identifier_normalized,
        }
        for product_id, source_identifier, search_identifier_value, search_identifier_normalized in rows
    ]


def create_scrape_run(
    conn: psycopg.Connection,
    run_id: uuid.UUID,
    competitor_id: int,
    started_at: datetime,
    queue_count: int,
    source_database: str,
    raw_file_path: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO scraper.scrape_run (
                run_id,
                competitor_id,
                started_at,
                status,
                last_heartbeat_at,
                last_progress,
                queue_count,
                search_success_count,
                not_found_count,
                error_count,
                offer_count,
                raw_file_path,
                raw_file_sha256,
                scraper_version,
                error_message
            ) VALUES (%s, %s, %s, 'RUNNING', %s, %s, %s, 0, 0, 0, 0, %s, NULL, %s, NULL)
            """,
            (
                run_id,
                competitor_id,
                started_at,
                started_at,
                "STARTED",
                queue_count,
                raw_file_path,
                f"{source_database}::profibagr_scraper",
            ),
        )


def mark_stale_scrape_runs(conn: psycopg.Connection, logger: logging.Logger) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE scraper.scrape_run
            SET status = 'ABORTED',
                finished_at = COALESCE(finished_at, now()),
                error_message = COALESCE(error_message, 'Stale scrape run without heartbeat')
            WHERE status = 'RUNNING'
              AND COALESCE(last_heartbeat_at, started_at) < now() - (%s || ' minutes')::interval
            RETURNING run_id
            """,
            (STALE_RUN_ABORT_MINUTES,),
        )
        aborted = cur.fetchall()
    if aborted:
        logger.error("ABORTED STALE RUNS: %s", ", ".join(str(row[0]) for row in aborted))
    return len(aborted)


def update_scrape_run_heartbeat(conn: psycopg.Connection, run_id: uuid.UUID, progress: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE scraper.scrape_run
            SET last_heartbeat_at = now(),
                last_progress = %s
            WHERE run_id = %s
            """,
            (progress, run_id),
        )


def register_signal_handlers(logger: logging.Logger, finalize_callback):
    def handler(signum, _frame):
        logger.error("RECEIVED SIGNAL %s", signum)
        finalize_callback("ABORTED", f"Received signal {signum}")
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def create_search_request(
    conn: psycopg.Connection,
    run_id: uuid.UUID,
    search_identifier: str,
) -> int:
    normalized = normalize_part_number(search_identifier)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO scraper.search_request (
                run_id,
                searched_identifier,
                searched_identifier_norm,
                requested_at,
                completed_at,
                status,
                match_count,
                http_status,
                error_type,
                error_message
            ) VALUES (%s, %s, %s, now(), NULL, 'RUNNING', NULL, NULL, NULL, NULL)
            RETURNING search_request_id
            """,
            (run_id, search_identifier, normalized),
        )
        return int(cur.fetchone()[0])


def record_search_request_products(
    conn: psycopg.Connection,
    search_request_id: int,
    products: list[dict[str, Any]],
) -> None:
    if not products:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO scraper.search_request_product (
                search_request_id,
                product_id,
                source_identifier
            ) VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            [
                (search_request_id, row["product_id"], row["source_identifier"])
                for row in products
            ],
        )


def record_offer_observations(
    conn: psycopg.Connection,
    search_request_id: int,
    rows: list[dict[str, Any]],
) -> None:
    offer_rows = [row for row in rows if row.get("status") == "OK"]
    if not offer_rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO scraper.offer_observation (
                search_request_id,
                found_identifier,
                found_identifier_norm,
                competitor_product_name,
                price_without_vat,
                price_with_vat,
                currency,
                availability_raw,
                product_url,
                observed_at,
                match_type,
                match_confidence
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s, %s
            )
            """,
            [
                (
                    search_request_id,
                    row.get("found_part_number") or None,
                    normalize_part_number_loose(row.get("found_part_number")),
                    row.get("product_name") or None,
                    Decimal(row["price_without_vat"]) if row.get("price_without_vat") else None,
                    Decimal(row["price_with_vat"]) if row.get("price_with_vat") else None,
                    row.get("currency") or None,
                    row.get("availability_raw") or None,
                    row.get("product_url") or None,
                    "STRICT" if normalize_part_number(row.get("search_part_number")) in normalize_part_number(row.get("found_part_number")) else "LOOSE",
                    Decimal("1.0000")
                    if normalize_part_number(row.get("search_part_number")) in normalize_part_number(row.get("found_part_number"))
                    else Decimal("0.7500"),
                )
                for row in offer_rows
            ],
        )


def finalize_search_request(
    conn: psycopg.Connection,
    search_request_id: int,
    result: FetchResult,
    finished_at: datetime,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE scraper.search_request
            SET completed_at = %s,
                status = %s,
                match_count = %s,
                http_status = NULL,
                error_type = CASE WHEN %s IN ('OK', 'NOT_FOUND') THEN NULL ELSE %s END,
                error_message = CASE WHEN %s IN ('OK', 'NOT_FOUND') THEN NULL ELSE %s END
            WHERE search_request_id = %s
            """,
            (
                finished_at,
                result.status,
                result.match_count,
                result.status,
                result.status,
                result.status,
                result.status,
                search_request_id,
            ),
        )


def finalize_scrape_run(
    conn: psycopg.Connection,
    run_id: uuid.UUID,
    finished_at: datetime,
    search_success_count: int,
    not_found_count: int,
    error_count: int,
    offer_count: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE scraper.scrape_run
            SET finished_at = %s,
                status = CASE WHEN %s = 0 THEN 'SUCCESS' WHEN %s > 0 AND %s > 0 THEN 'PARTIAL' ELSE 'FAILED' END,
                last_heartbeat_at = now(),
                search_success_count = %s,
                not_found_count = %s,
                error_count = %s,
                offer_count = %s
            WHERE run_id = %s
            """,
            (
                finished_at,
                error_count,
                error_count,
                search_success_count,
                search_success_count,
                not_found_count,
                error_count,
                offer_count,
                run_id,
            ),
        )


def parse_search_product_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    cards = soup.select("#snippet-searchedProducts-productList article.card-item")
    for card in cards:
        anchor = card.select_one("h4 a[href]") or card.select_one("a[href]")
        if not anchor:
            continue
        href = anchor.get("href", "").strip()
        if not href:
            continue
        urls.append(urljoin(BASE_URL, href))

    # fallback when card structure changes
    if not urls:
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "")
            if href.startswith("/p/"):
                urls.append(urljoin(BASE_URL, href))

    deduped: list[str] = []
    seen: set[str] = set()
    for item in urls:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def extract_oem_from_detail(soup: BeautifulSoup) -> str:
    for row in soup.select("div.row"):
        cols = row.find_all("div", recursive=False)
        if len(cols) < 2:
            continue
        label = " ".join(cols[0].stripped_strings)
        if "OEM" in label.upper():
            value = " ".join(cols[1].stripped_strings)
            if value:
                return value
    return ""


def extract_availability_raw(soup: BeautifulSoup) -> str:
    availability = soup.select_one("#snippet--availabilityAjax abbr")
    if availability:
        return " ".join(availability.get_text(" ", strip=True).split())

    availability = soup.select_one(".availability")
    if availability:
        return " ".join(availability.get_text(" ", strip=True).split())

    return ""


def parse_product_detail(html: str, product_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    upgates = parse_upgates_json(html) or {}
    upgates_product = upgates.get("product") or {}
    upgates_price = upgates_product.get("price") or {}

    product_name = upgates_product.get("title")
    if not product_name:
        h1 = soup.select_one("h1")
        product_name = h1.get_text(" ", strip=True) if h1 else ""

    found_part_number = extract_oem_from_detail(soup) or str(upgates_product.get("code", ""))

    without_vat = None
    with_vat = None

    if upgates_price:
        if upgates_price.get("withoutVat") is not None:
            without_vat = Decimal(str(upgates_price["withoutVat"])).quantize(Decimal("0.01"))
        if upgates_price.get("withVat") is not None:
            with_vat = Decimal(str(upgates_price["withVat"])).quantize(Decimal("0.01"))

    if without_vat is None:
        without_vat = parse_price_decimal(
            soup.select_one(".pd-price .price-main").get_text(" ", strip=True)
            if soup.select_one(".pd-price .price-main")
            else None
        )

    if with_vat is None:
        with_vat = parse_price_decimal(
            soup.select_one(".pd-price .price-other").get_text(" ", strip=True)
            if soup.select_one(".pd-price .price-other")
            else None
        )

    currency = upgates.get("currency") or "CZK"
    availability_raw = extract_availability_raw(soup)

    return {
        "found_part_number": found_part_number,
        "product_name": product_name,
        "price_without_vat": without_vat,
        "price_with_vat": with_vat,
        "currency": currency,
        "availability_raw": availability_raw,
        "product_url": product_url,
    }


def status_row(
    run_id: str,
    search_part_number: str,
    status: str,
    match_count: int,
    scraped_at: str,
    http_status: int | None = None,
    error_type: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "scraped_at": scraped_at,
        "search_part_number": search_part_number,
        "status": status,
        "match_count": match_count,
        "found_part_number": "",
        "product_name": "",
        "price_without_vat": "",
        "price_with_vat": "",
        "currency": "",
        "availability_raw": "",
        "product_url": "",
        "http_status": http_status or "",
        "error_type": error_type,
        "error_message": error_message,
    }


def scrape_part_number(
    client: httpx.Client,
    run_id: str,
    search_part_number: str,
    logger: logging.Logger,
) -> FetchResult:
    scraped_at = datetime.now(timezone.utc).isoformat()
    logger.info("SEARCH: %s", search_part_number)

    try:
        response = client.get(SEARCH_PATH, params={"phrase": search_part_number})
    except httpx.TimeoutException as exc:
        logger.error("TIMEOUT: %s", search_part_number)
        return FetchResult(
            status="TIMEOUT",
            match_count=0,
            rows=[
                status_row(
                    run_id,
                    search_part_number,
                    "TIMEOUT",
                    0,
                    scraped_at,
                    error_type="TIMEOUT",
                    error_message=str(exc),
                )
            ],
        )
    except httpx.HTTPError as exc:
        logger.error("HTTP ERROR: %s", search_part_number)
        return FetchResult(
            status="HTTP_ERROR",
            match_count=0,
            rows=[
                status_row(
                    run_id,
                    search_part_number,
                    "HTTP_ERROR",
                    0,
                    scraped_at,
                    error_type="HTTP_ERROR",
                    error_message=str(exc),
                )
            ],
        )

    if response.status_code in (403, 429):
        logger.error("BLOCKED: %s (%s)", search_part_number, response.status_code)
        return FetchResult(
            status="BLOCKED",
            match_count=0,
            rows=[
                status_row(
                    run_id,
                    search_part_number,
                    "BLOCKED",
                    0,
                    scraped_at,
                    http_status=response.status_code,
                    error_type="BLOCKED",
                    error_message="Possible anti-bot protection.",
                )
            ],
        )

    if response.status_code >= 400:
        logger.error("HTTP ERROR: %s (%s)", search_part_number, response.status_code)
        return FetchResult(
            status="HTTP_ERROR",
            match_count=0,
            rows=[
                status_row(
                    run_id,
                    search_part_number,
                    "HTTP_ERROR",
                    0,
                    scraped_at,
                    http_status=response.status_code,
                    error_type="HTTP_ERROR",
                    error_message=f"Search returned HTTP {response.status_code}",
                )
            ],
        )

    product_urls = parse_search_product_urls(response.text)
    logger.info("RESULT COUNT: %s for %s", len(product_urls), search_part_number)

    if not product_urls:
        logger.info("NOT FOUND: %s", search_part_number)
        return FetchResult(
            status="NOT_FOUND",
            match_count=0,
            rows=[status_row(run_id, search_part_number, "NOT_FOUND", 0, scraped_at)],
        )

    rows: list[dict[str, Any]] = []
    for product_url in product_urls:
        logger.info("PRODUCT URL: %s", product_url)
        try:
            detail = client.get(product_url)
        except httpx.TimeoutException as exc:
            rows.append(
                status_row(
                    run_id,
                    search_part_number,
                    "TIMEOUT",
                    len(product_urls),
                    scraped_at,
                    error_type="TIMEOUT",
                    error_message=str(exc),
                )
            )
            continue
        except httpx.HTTPError as exc:
            rows.append(
                status_row(
                    run_id,
                    search_part_number,
                    "HTTP_ERROR",
                    len(product_urls),
                    scraped_at,
                    error_type="HTTP_ERROR",
                    error_message=str(exc),
                )
            )
            continue

        if detail.status_code >= 400:
            rows.append(
                status_row(
                    run_id,
                    search_part_number,
                    "HTTP_ERROR",
                    len(product_urls),
                    scraped_at,
                    http_status=detail.status_code,
                    error_type="HTTP_ERROR",
                    error_message=f"Detail returned HTTP {detail.status_code}",
                )
            )
            continue

        try:
            parsed = parse_product_detail(detail.text, product_url)
            logger.info(
                "PRICE: %s / %s",
                decimal_to_str(parsed["price_without_vat"]),
                decimal_to_str(parsed["price_with_vat"]),
            )

            strict_match = normalize_part_number(search_part_number) in normalize_part_number(
                parsed["found_part_number"]
            )
            loose_match = normalize_part_number_loose(search_part_number) in normalize_part_number_loose(
                parsed["found_part_number"]
            )
            logger.info(
                "MATCH INFO: strict=%s loose=%s found=%s",
                strict_match,
                loose_match,
                parsed["found_part_number"],
            )

            rows.append(
                {
                    "run_id": run_id,
                    "scraped_at": scraped_at,
                    "search_part_number": search_part_number,
                    "status": "OK",
                    "match_count": len(product_urls),
                    "found_part_number": parsed["found_part_number"],
                    "product_name": parsed["product_name"],
                    "price_without_vat": decimal_to_str(parsed["price_without_vat"]),
                    "price_with_vat": decimal_to_str(parsed["price_with_vat"]),
                    "currency": parsed["currency"],
                    "availability_raw": parsed["availability_raw"],
                    "product_url": parsed["product_url"],
                    "http_status": detail.status_code,
                    "error_type": "",
                    "error_message": "",
                }
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("PARSER ERROR on %s", product_url)
            rows.append(
                status_row(
                    run_id,
                    search_part_number,
                    "PARSER_ERROR",
                    len(product_urls),
                    scraped_at,
                    http_status=detail.status_code,
                    error_type="PARSER_ERROR",
                    error_message=str(exc),
                )
            )

    if not rows:
        return FetchResult(
            status="UNEXPECTED_RESPONSE",
            match_count=0,
            rows=[
                status_row(
                    run_id,
                    search_part_number,
                    "UNEXPECTED_RESPONSE",
                    0,
                    scraped_at,
                    http_status=response.status_code,
                    error_type="UNEXPECTED_RESPONSE",
                    error_message="Search returned links but no rows were parsed.",
                )
            ],
        )

    overall_status = "OK" if any(row.get("status") == "OK" for row in rows) else rows[0]["status"]
    return FetchResult(status=overall_status, match_count=len(product_urls), rows=rows)


def abort_scrape_run(
    conn: psycopg.Connection,
    run_id: uuid.UUID,
    finished_at: datetime,
    message: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE scraper.scrape_run
            SET finished_at = %s,
                status = 'ABORTED',
                last_heartbeat_at = %s,
                error_message = %s
            WHERE run_id = %s
            """,
            (finished_at, finished_at, message, run_id),
        )


def write_csv(output_path: Path, rows: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_HEADERS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profibagr scraper PoC")
    parser.add_argument(
        "--part-number",
        action="append",
        dest="part_numbers",
        help="Manual part number search (can be used multiple times).",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent / ".env")
    args = parse_args()
    request_delay_seconds = get_request_delay_seconds()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    scrape_run_id = uuid.uuid4()
    base_dir = Path(__file__).resolve().parent
    logs_dir = base_dir / "logs"
    data_dir = base_dir / "data" / "raw" / "profibagr"
    csv_path = data_dir / f"profibagr_{run_id}.csv"

    logger = setup_logging(run_id, logs_dir)

    if args.part_numbers:
        part_numbers = [normalize_part_number(value) for value in args.part_numbers if value]
    else:
        try:
            part_numbers = fetch_part_numbers_from_db(logger)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("DATABASE ERROR")
            logger.error("END")
            print(f"Database error: {exc}")
            return 1

    part_numbers = [pn for pn in part_numbers if pn]
    logger.info("INPUT COUNT: %s", len(part_numbers))

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/127.0.0.0 Safari/537.36 ProfibagrScraperPoC/1.0"
        ),
        "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
    }

    all_rows: list[dict[str, Any]] = []
    search_success_count = 0
    not_found_count = 0
    error_count = 0
    offer_count = 0
    finalized = False
    scrape_run_status = "RUNNING"
    scrape_run_message = ""

    try:
        monitor_conn = connect_monitor_db()
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("MONITOR DATABASE ERROR")
        logger.error("END")
        print(f"Monitor database error: {exc}")
        return 1

    try:
        competitor_id = ensure_competitor_id(monitor_conn)
        mark_stale_scrape_runs(monitor_conn, logger)
        create_scrape_run(
            monitor_conn,
            run_id=scrape_run_id,
            competitor_id=competitor_id,
            started_at=datetime.now(timezone.utc),
            queue_count=len(part_numbers),
            source_database=get_env_or_raise("POHODA_DB_NAME"),
            raw_file_path=str(csv_path),
        )

        def finalize_run(status: str, message: str = "") -> None:
            nonlocal finalized, scrape_run_status, scrape_run_message
            if finalized:
                return
            scrape_run_status = status
            scrape_run_message = message
            if status == "ABORTED":
                abort_scrape_run(monitor_conn, scrape_run_id, datetime.now(timezone.utc), message or "Aborted")
            else:
                finalize_scrape_run(
                    monitor_conn,
                    scrape_run_id,
                    datetime.now(timezone.utc),
                    search_success_count=search_success_count,
                    not_found_count=not_found_count,
                    error_count=error_count,
                    offer_count=offer_count,
                )
            finalized = True

        register_signal_handlers(logger, finalize_run)

        with httpx.Client(base_url=BASE_URL, headers=headers, timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            for index, part_number in enumerate(part_numbers):
                logger.info("PROGRESS %s/%s: %s", index + 1, len(part_numbers), part_number)
                update_scrape_run_heartbeat(monitor_conn, scrape_run_id, f"SEARCHING {index + 1}/{len(part_numbers)} {part_number}")
                search_request_id = None
                try:
                    products = resolve_products_for_search_identifier(monitor_conn, part_number)
                    search_request_id = create_search_request(monitor_conn, scrape_run_id, part_number)
                    record_search_request_products(monitor_conn, search_request_id, products)
                    result = scrape_part_number(client, run_id, part_number, logger)
                    record_offer_observations(monitor_conn, search_request_id, result.rows)
                    finalize_search_request(monitor_conn, search_request_id, result, datetime.now(timezone.utc))
                    update_scrape_run_heartbeat(monitor_conn, scrape_run_id, f"DONE {index + 1}/{len(part_numbers)} {part_number} {result.status}")
                except Exception as exc:  # pylint: disable=broad-except
                    logger.exception("MONITOR WRITE ERROR on %s", part_number)
                    if search_request_id is not None:
                        try:
                            with monitor_conn.cursor() as cur:
                                cur.execute(
                                    """
                                    UPDATE scraper.search_request
                                    SET completed_at = %s,
                                        status = 'FAILED',
                                        match_count = COALESCE(match_count, 0),
                                        http_status = NULL,
                                        error_type = 'FAILED',
                                        error_message = %s
                                    WHERE search_request_id = %s
                                    """,
                                    (datetime.now(timezone.utc), str(exc), search_request_id),
                                )
                        except Exception:  # pylint: disable=broad-except
                            pass
                    error_count += 1
                    update_scrape_run_heartbeat(monitor_conn, scrape_run_id, f"ERROR {index + 1}/{len(part_numbers)} {part_number}")
                    break

                all_rows.extend(result.rows)
                if result.status == "OK":
                    search_success_count += 1
                    offer_count += sum(1 for row in result.rows if row.get("status") == "OK")
                elif result.status == "NOT_FOUND":
                    not_found_count += 1
                else:
                    error_count += 1

                if index < len(part_numbers) - 1:
                    time.sleep(request_delay_seconds)

        finalize_run("SUCCESS" if error_count == 0 else "PARTIAL", scrape_run_message)
    except Exception as exc:  # pylint: disable=broad-except
        try:
            finalize_run("FAILED", str(exc))
        except Exception:  # pylint: disable=broad-except
            monitor_conn.rollback()
        logger.exception("DATABASE ERROR")
        logger.error("END")
        print(f"Database error: {exc}")
        return 1
    finally:
        if not finalized:
            try:
                abort_scrape_run(monitor_conn, scrape_run_id, datetime.now(timezone.utc), scrape_run_message or "Process ended without clean finalization")
            except Exception:  # pylint: disable=broad-except
                monitor_conn.rollback()
        monitor_conn.close()

    write_csv(csv_path, all_rows)
    logger.info("CSV CREATED: %s", csv_path)
    logger.info("END")

    print(csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
