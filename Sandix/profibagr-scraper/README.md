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
| `B2B_COGITO` | `https://b2bcogito.com` | `competitors/b2b_cogito.env.example` |

Competitor files contain only website-specific settings. The scraper always loads database access from `profibagr-scraper/.env` first, then applies the selected competitor file.

## Scopes

| Scope | Source | Use |
| --- | --- | --- |
| `queue` | `scraper.v_search_queue`, at most 5000 source identifiers | Normal recurring run |
| `full` | All current Sandix identifiers from `core.product_search_identifier_v` | Full coverage run; can take many hours |

Before HTTP requests, suffix variants are collapsed to unique base part numbers. A full run currently resolves to roughly 10,302 unique base identifiers.

## How Search Identifiers Are Prepared

The scraper does not search the raw POHODA `IDS` value directly. Identifiers pass through these stages:

1. `source_pohoda.stock_current.ids` stores the raw `IDS` value imported from POHODA.
2. `core.product_search_identifier_v` splits each raw value into individual tokens separated by whitespace, comma, semicolon, or `|`. This view is the source for `--scope full`.
3. `scraper.v_search_queue` selects eligible tokens from the same view for `--scope queue`; it filters to web-enabled products with available stock and removes duplicate normalized tokens. It does not remove replacement suffixes.
4. At scraper startup, `fetch_part_numbers_from_db()` loads active suffixes from `sandix_price_analytics.reporting.variant_suffix_catalog_v` and calls `dedupe_part_numbers_by_base()`.
5. `dedupe_part_numbers_by_base()` removes configured replacement suffixes and deduplicates the resulting base PN. This in-memory list is the final input sent to competitor websites.

For example, the raw POHODA value:

```text
332/G8146a 128/11789a 400/V8268a
```

produces three individual search tokens:

```text
332/G8146A
128/11789A
400/V8268A
```

Suffix variants are then collapsed before the HTTP request. For example:

```text
02/100284AB
02/100284AD
02/100284AH
```

produce one final search request:

```text
02/100284
```

The final suffix-cleaned list is intentionally not materialized in `scraper.v_search_queue`; it exists only while the scraper runs. After a run starts, the exact values sent to the competitor are stored in `scraper.search_request.searched_identifier`.

```sql
SELECT searched_identifier, status, requested_at
FROM scraper.search_request
WHERE run_id = '<run_uuid>'
ORDER BY search_request_id;
```

`core.product_search_identifier_v` and `scraper.v_search_queue` are dynamic PostgreSQL views. A newly started run reads their current tokenized values, while a run that is already in progress keeps the input list that it loaded at startup.

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

## Profimachinery, Dílybagru, Strojparts, And B2B Cogito

All four use a checked-in website configuration template. The following commands run a one-part smoke test without modifying your default Profibagr `.env`.

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

B2B Cogito:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
COMPETITOR_ENV_FILE="$PWD/profibagr-scraper/competitors/b2b_cogito.env.example" .venv_scraper/bin/python profibagr-scraper/profibagr_scraper.py --part-number "32/925895"
```

Normal queue run for any of these competitors uses the same command with `--scope queue` instead of `--part-number`.

Use the full sequential pipeline after the smoke test passes. Example for Dílybagru:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
COMPETITOR_ENV_FILE="$PWD/profibagr-scraper/competitors/dilybagru.env.example" .venv_scraper/bin/python analytics-etl/run_competitor_pipeline.py --scope queue
```

Dílybagru publishes its product prices with VAT only; the scraper derives net price using Czech 21% VAT. Strojparts uses a JSON API and may return a product with no public price. Such zero/missing prices are stored for audit but excluded from price-gap reporting. B2B Cogito publishes both net and gross prices in EUR. It uses one stable outbound connection, waits five seconds between part-number searches, and does not rotate proxies.

For B2B Cogito, `403`, `429`, `503`, and CAPTCHA redirect responses trigger exponential backoff: the scraper retries after 60 seconds and then 120 seconds. If protection remains active, it stops the entire run with status `BLOCKED`; the run is excluded from analytics and no further requests are sent. The retry values are configurable in `competitors/b2b_cogito.env.example`.

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

## Find And Stop Running Processes

Find all active scraper and pipeline processes:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
pgrep -af 'profibagr_scraper.py|run_competitor_pipeline.py|analytics_etl.py|part_number_filter_etl.py'
```

Stop a standalone scraper with its PID:

```bash
kill -TERM <scraper_pid>
```

When the scraper was launched through `run_competitor_pipeline.py`, stop both the pipeline PID and its active scraper PID. This prevents the pipeline from continuing with ETL or another scraper after the current run exits:

```bash
kill -TERM <pipeline_pid> <scraper_pid>
```

The scraper handles `SIGTERM` by marking the active database run as `ABORTED`. Wait a few seconds, then confirm that no process remains:

```bash
sleep 3
pgrep -af 'profibagr_scraper.py|run_competitor_pipeline.py|analytics_etl.py|part_number_filter_etl.py'
```
