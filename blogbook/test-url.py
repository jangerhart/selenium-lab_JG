#!/usr/bin/env python3

import csv
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests


INPUT_FILE = "urls.txt"
OUTPUT_FILE = "url_check_results.csv"

TIMEOUT = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0 Safari/537.36"
    )
}


def is_valid_url(url: str) -> bool:
    """Ověří základní syntaktickou platnost URL."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except ValueError:
        return False


def check_url(url: str) -> dict:
    """Ověří dostupnost URL a vrátí výsledek kontroly."""
    result = {
        "url": url,
        "valid_format": False,
        "reachable": False,
        "status_code": "",
        "final_url": "",
        "redirected": False,
        "error": "",
    }

    if not is_valid_url(url):
        result["error"] = "Neplatný formát URL"
        return result

    result["valid_format"] = True

    try:
        # GET je spolehlivější než HEAD, protože některé weby HEAD blokují.
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        result["status_code"] = response.status_code
        result["final_url"] = response.url
        result["redirected"] = response.url.rstrip("/") != url.rstrip("/")

        # Za dostupné považujeme odpovědi 2xx a 3xx.
        result["reachable"] = 200 <= response.status_code < 400

        if not result["reachable"]:
            result["error"] = f"HTTP chyba {response.status_code}"

        response.close()

    except requests.exceptions.Timeout:
        result["error"] = f"Timeout po {TIMEOUT} sekundách"

    except requests.exceptions.SSLError as exc:
        result["error"] = f"SSL chyba: {exc}"

    except requests.exceptions.ConnectionError as exc:
        result["error"] = f"Chyba připojení: {exc}"

    except requests.exceptions.RequestException as exc:
        result["error"] = f"HTTP chyba: {exc}"

    return result


def load_urls(path: Path) -> list[str]:
    """Načte URL, odstraní prázdné řádky, komentáře a duplicity."""
    urls = []
    seen = set()

    with path.open("r", encoding="utf-8-sig") as file:
        for line in file:
            url = line.strip()

            if not url or url.startswith("#"):
                continue

            if url not in seen:
                seen.add(url)
                urls.append(url)

    return urls


def main() -> int:
    input_path = Path(INPUT_FILE)
    output_path = Path(OUTPUT_FILE)

    if not input_path.exists():
        print(f"Chyba: soubor {input_path} neexistuje.")
        return 1

    urls = load_urls(input_path)

    if not urls:
        print(f"Soubor {input_path} neobsahuje žádné URL.")
        return 1

    print(f"Kontroluji {len(urls)} URL...")

    results = []

    for index, url in enumerate(urls, start=1):
        print(f"[{index}/{len(urls)}] {url}")

        result = check_url(url)
        results.append(result)

        if result["reachable"]:
            redirect_info = ""
            if result["redirected"]:
                redirect_info = f" -> {result['final_url']}"

            print(f"  OK, HTTP {result['status_code']}{redirect_info}")
        else:
            print(f"  CHYBA: {result['error']}")

    fieldnames = [
        "url",
        "valid_format",
        "reachable",
        "status_code",
        "final_url",
        "redirected",
        "error",
    ]

    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(results)

    successful = sum(result["reachable"] for result in results)
    failed = len(results) - successful

    print()
    print("Kontrola dokončena.")
    print(f"Funkční URL:   {successful}")
    print(f"Nefunkční URL: {failed}")
    print(f"Výsledky:      {output_path}")

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())