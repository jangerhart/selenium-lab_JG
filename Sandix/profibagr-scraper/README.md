# Competitor Scraper

Shared HTTP scraper for competitor price monitoring. The filename remains `profibagr_scraper.py`, but the scraper is configured by environment variables and supports Profibagr, Bagry ND, Profimachinery, Dílybagru, and Strojparts.

## What It Does

1. Reads Sandix part numbers from PostgreSQL.
2. Searches each part number on the configured competitor website.
3. Stores each scrape run, request, and offer in `sandix_price_monitor`.
4. Writes a RAW CSV audit file and a log file.

The scraper does not build reporting snapshots. After a raw scraper run, use the shared pipeline wrapper or run the analytics ETL steps separately.

## One-Time Setup

Run this once from the project root:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
python3 -m venv .venv_scraper
.venv_scraper/bin/pip install -r profibagr-scraper/requirements.txt
cp profibagr-scraper/.env.example profibagr-scraper/.env
```

Fill `profibagr-scraper/.env` with database access. The scraper should use the read-only account:

```dotenv
SCRAPER_DB_USER=price_scraper_ro
```

All examples below activate `.venv_scraper`. If it is already active, start from the second line of the relevant block.

## Available Competitors

| Code | Website | Configuration file |
| --- | --- | --- |
| `PROFIBAGR` | `https://www.profibagr.cz` | default `profibagr-scraper/.env` |
| `BAGRY_ND` | `https://www.jcb-nahradni-dily.cz` | `competitors/bagry_nd.env.example` |
| `PROFI_MACHINERY` | `https://www.profimachinery.cz` | `competitors/profi_machinery.env.example` |
| `DILYBAGRU` | `https://www.dilybagru.cz` | `competitors/dilybagru.env.example` |
| `STROJPARTS` | `https://www.strojparts.cz` | `competitors/strojparts.env.example` |

Competitor files contain only website-specific settings. The scraper always loads database access from `profibagr-scraper/.env` first, then applies the selected competitor file.

## Scopes

| Scope | Source | Use |
| --- | --- | --- |
| `queue` | `scraper.v_search_queue`, at most 5000 source identifiers | Normal recurring run |
| `full` | All current Sandix identifiers from `core.product_search_identifier_v` | Full coverage run; can take many hours |

Before HTTP requests, suffix variants are collapsed to unique base part numbers. A full run currently resolves to roughly 10,302 unique base identifiers.

## Profibagr

The default `.env` configuration is Profibagr. Copy-paste a normal queue run:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
source .venv_scraper/bin/activate
python3 profibagr-scraper/profibagr_scraper.py --scope queue
```

Copy-paste a full run in the foreground:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
source .venv_scraper/bin/activate
python3 profibagr-scraper/profibagr_scraper.py --scope full
```

Recommended full run in the background:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
nohup .venv_scraper/bin/python profibagr-scraper/profibagr_scraper.py --scope full > profibagr-scraper/logs/profibagr_full.log 2>&1 &
tail -f profibagr-scraper/logs/profibagr_full.log
```

Test one or more known part numbers before a long run:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
source .venv_scraper/bin/activate
python3 profibagr-scraper/profibagr_scraper.py --part-number "980/88215" --part-number "32/925895"
```

## Bagry ND

Bagry ND uses the same database credentials from `profibagr-scraper/.env`. The command below overrides only competitor-specific settings, so it can be pasted directly into the activated environment.

Queue run:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
source .venv_scraper/bin/activate
COMPETITOR_CODE=BAGRY_ND COMPETITOR_NAME="Bagry ND" BASE_URL=https://www.jcb-nahradni-dily.cz SEARCH_PATH=/hledani SEARCH_PARAM=query python3 profibagr-scraper/profibagr_scraper.py --scope queue
```

Full run in the background:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
nohup env COMPETITOR_CODE=BAGRY_ND COMPETITOR_NAME="Bagry ND" BASE_URL=https://www.jcb-nahradni-dily.cz SEARCH_PATH=/hledani SEARCH_PARAM=query .venv_scraper/bin/python profibagr-scraper/profibagr_scraper.py --scope full > profibagr-scraper/logs/bagry_nd_full.log 2>&1 &
tail -f profibagr-scraper/logs/bagry_nd_full.log
```

Manual Bagry ND test:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
source .venv_scraper/bin/activate
COMPETITOR_CODE=BAGRY_ND COMPETITOR_NAME="Bagry ND" BASE_URL=https://www.jcb-nahradni-dily.cz SEARCH_PATH=/hledani SEARCH_PARAM=query python3 profibagr-scraper/profibagr_scraper.py --part-number "32/925895"
```

For a persistent Bagry ND configuration, create a competitor `.env` file with its website settings, then run:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
COMPETITOR_ENV_FILE=/absolute/path/to/bagry-nd.env .venv_scraper/bin/python profibagr-scraper/profibagr_scraper.py --scope queue
```

## Profimachinery, Dílybagru, And Strojparts

All three use a checked-in website configuration template. The following commands run a one-part smoke test without modifying your default Profibagr `.env`.

Profimachinery:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
COMPETITOR_ENV_FILE="$PWD/profibagr-scraper/competitors/profi_machinery.env.example" .venv_scraper/bin/python profibagr-scraper/profibagr_scraper.py --part-number "32/925895"
```

Dílybagru:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
COMPETITOR_ENV_FILE="$PWD/profibagr-scraper/competitors/dilybagru.env.example" .venv_scraper/bin/python profibagr-scraper/profibagr_scraper.py --part-number "32/925895"
```

Strojparts:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
COMPETITOR_ENV_FILE="$PWD/profibagr-scraper/competitors/strojparts.env.example" .venv_scraper/bin/python profibagr-scraper/profibagr_scraper.py --part-number "32/925895"
```

Normal queue run for any of these competitors uses the same command with `--scope queue` instead of `--part-number`.

Use the full sequential pipeline after the smoke test passes. Example for Dílybagru:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
COMPETITOR_ENV_FILE="$PWD/profibagr-scraper/competitors/dilybagru.env.example" .venv_scraper/bin/python analytics-etl/run_competitor_pipeline.py --scope queue
```

Dílybagru publishes its product prices with VAT only; the scraper derives net price using Czech 21% VAT. Strojparts uses a JSON API and may return a product with no public price. Such zero/missing prices are stored for audit but excluded from price-gap reporting.

## After The Scraper

For a manual scraper run, wait for it to finish. A `SUCCESS` run is complete without request errors; a `PARTIAL` run processed all inputs but had some request errors. Both are included by the analytics ETL. Do not run analytics for `ABORTED` runs.

Run the two reporting steps for Profibagr:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix/analytics-etl
../.venv_scraper/bin/python analytics_etl.py
../.venv_scraper/bin/python part_number_filter_etl.py
```

For the next scheduled run, prefer the pipeline wrapper instead of launching the three stages manually:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
.venv_scraper/bin/python analytics-etl/run_competitor_pipeline.py --scope queue
```

For Bagry ND, add the same inline competitor variables from the Bagry ND examples before `.venv_scraper/bin/python`.

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
COMPETITOR_CODE=BAGRY_ND COMPETITOR_NAME="Bagry ND" BASE_URL=https://www.jcb-nahradni-dily.cz SEARCH_PATH=/hledani SEARCH_PARAM=query .venv_scraper/bin/python analytics-etl/run_competitor_pipeline.py --scope queue
```

## Outputs And Monitoring

- CSV: `profibagr-scraper/data/raw/<competitor>/<competitor>_YYYYMMDD_HHMMSS.csv`
- Per-run log: `profibagr-scraper/logs/<competitor>_YYYYMMDD_HHMMSS.log`
- Background command log: the explicit `profibagr_full.log` or `bagry_nd_full.log` path in the command above
- DB state: `sandix_price_monitor.scraper.scrape_run`, `search_request`, and `offer_observation`

For a background run, use `tail -f` on its explicit log file. The final log line and database run status distinguish `SUCCESS`, `PARTIAL`, and `ABORTED`.
