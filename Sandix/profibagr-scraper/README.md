# Profibagr Scraper

Profibagr scraper for price monitoring on `https://www.profibagr.cz/`.

## What it does

- reads up to 100 search identifiers from PostgreSQL view `scraper.v_search_queue`
- searches each part number on Profibagr
- opens product detail pages and extracts key fields
- writes output into CSV (`;` delimiter, UTF-8)
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

## Run

Batch run from DB:

```bash
python3 profibagr_scraper.py
```

Manual single part test:

```bash
python3 profibagr_scraper.py --part-number "980/88215"
```

## Outputs

- CSV: `data/raw/profibagr/profibagr_YYYYMMDD_HHMMSS.csv`
- log: `logs/profibagr_YYYYMMDD_HHMMSS.log`
