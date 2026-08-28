import argparse
import csv
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
import psycopg
from bs4 import BeautifulSoup
from dotenv import load_dotenv


BASE_URL = "https://www.profibagr.cz"
SEARCH_PATH = "/search"
SEARCH_SUGGEST_PATH = "/search/suggest"
REQUEST_TIMEOUT_SECONDS = 15
REQUEST_DELAY_SECONDS = 1
DB_QUERY = """
SELECT search_part_number
FROM scraper.v_profibagr_search_queue
WHERE btrim(search_part_number_normalized) ~ '^[A-Z0-9][A-Z0-9/.-]*[A-Z0-9]$'
  AND btrim(search_part_number_normalized) ~ '[0-9]'
  AND length(regexp_replace(search_part_number_normalized, '[^[:alnum:]]', '', 'g')) >= 5
ORDER BY search_part_number
LIMIT 100;
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
    rows: list[dict[str, Any]]


def normalize_part_number(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().upper()


def normalize_part_number_loose(value: str | None) -> str:
    normalized = normalize_part_number(value)
    return re.sub(r"[\s\-/]", "", normalized)


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
    host = get_env_or_raise("SCRAPER_DB_HOST")
    port = get_env_or_raise("SCRAPER_DB_PORT")
    db_name = get_env_or_raise("SCRAPER_DB_NAME")
    user = get_env_or_raise("SCRAPER_DB_USER")
    password = get_env_or_raise("SCRAPER_DB_PASSWORD")

    if user != "price_scraper_ro":
        logger.warning("SCRAPER_DB_USER is %s, expected price_scraper_ro", user)

    conninfo = (
        f"host={host} port={port} dbname={db_name} "
        f"user={user} password={password}"
    )

    with psycopg.connect(conninfo, options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            cur.execute(DB_QUERY)
            rows = cur.fetchall()

    logger.info("DATABASE CONNECTED")

    seen: set[str] = set()
    unique_parts: list[str] = []
    for row in rows:
        value = normalize_part_number(str(row[0]))
        if value and value not in seen:
            seen.add(value)
            unique_parts.append(value)

    return unique_parts[:100]


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
    return FetchResult(status=overall_status, rows=rows)


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
    load_dotenv()
    args = parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
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
    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
        for index, part_number in enumerate(part_numbers):
            result = scrape_part_number(client, run_id, part_number, logger)
            all_rows.extend(result.rows)
            if index < len(part_numbers) - 1:
                time.sleep(REQUEST_DELAY_SECONDS)

    write_csv(csv_path, all_rows)
    logger.info("CSV CREATED: %s", csv_path)
    logger.info("END")

    print(csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
