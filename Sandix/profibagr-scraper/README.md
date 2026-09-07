# Profibagr Scraper

Profibagr scraper for price monitoring on `https://www.profibagr.cz/`.

## What it does

- reads up to 500 search identifiers from PostgreSQL view `scraper.v_search_queue`, then collapses suffix variants to unique base PN before scraping
- can also run in full-scope mode over all Sandix current identifiers from `core.product_search_identifier_v`
- searches each part number on Profibagr
- opens product detail pages and extracts key fields
- writes output into CSV (`;` delimiter, UTF-8)
- updates `scraper.scrape_run` heartbeat/progress and aborts stale runs on startup
- writes run log file
- writes run history and observations into `sandix_price_monitor`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `.env` with DB credentials. Use read-only user:

`SCRAPER_DB_USER=price_scraper_ro`

Optional pacing:

`REQUEST_DELAY_SECONDS=3`

## Run

Batch run from DB:

```bash
python3 profibagr_scraper.py
```

If the current interpreter does not have the dependencies installed, the script auto-reexecs into `.venv_scraper/bin/python` when that venv exists.

Full Sandix scope:

```bash
python3 profibagr_scraper.py --scope full
```

This reads all current Sandix identifiers, strips variant suffixes, and searches only unique base PN values.

Manual single part test:

```bash
python3 profibagr_scraper.py --part-number "980/88215"
```

Cron example:

```bash
PYTHONPATH=src /path/to/.venv_scraper/bin/python profibagr_scraper.py --scope full >> logs/cron_profibagr.log 2>&1
```

## Outputs

- CSV: `data/raw/profibagr/profibagr_YYYYMMDD_HHMMSS.csv`
- log: `logs/profibagr_YYYYMMDD_HHMMSS.log`
