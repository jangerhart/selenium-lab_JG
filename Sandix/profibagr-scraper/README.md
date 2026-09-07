# Competitor Scraper

Shared scraper for competitor price monitoring.

## What it does

- reads up to 500 search identifiers from PostgreSQL view `scraper.v_search_queue`, then collapses suffix variants to unique base PN before scraping
- can also run in full-scope mode over all Sandix current identifiers from `core.product_search_identifier_v`
- searches each part number on the configured competitor site
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

Set `.env` with DB credentials and competitor settings. Use read-only user:

`SCRAPER_DB_USER=price_scraper_ro`

Default competitor settings keep Profibagr behavior. For `bagry-nd`, set:

```bash
COMPETITOR_CODE=BAGRY_ND
COMPETITOR_NAME=Bagry ND
BASE_URL=https://www.jcb-nahradni-dily.cz
SEARCH_PATH=/hledani
SEARCH_PARAM=query
```

Optional pacing:

`REQUEST_DELAY_SECONDS=3`

## Run

Batch run from DB:

```bash
python3 profibagr_scraper.py
```

If the current interpreter does not have the dependencies installed, the script auto-reexecs into `.venv_scraper/bin/python` when that venv exists.

Recommended background run:

```bash
nohup /path/to/.venv_scraper/bin/python profibagr_scraper.py --scope full > logs/run.log 2>&1 &
tail -f logs/run.log
```

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
PYTHONPATH=src /path/to/.venv_scraper/bin/python profibagr_scraper.py --scope full >> logs/cron_competitor.log 2>&1
```

For interactive debugging, prefer `tail -f` on the log file over keeping the scraper attached to the terminal.

## Outputs

- CSV: `data/raw/<competitor>/<competitor>_YYYYMMDD_HHMMSS.csv`
- log: `logs/<competitor>_YYYYMMDD_HHMMSS.log`
