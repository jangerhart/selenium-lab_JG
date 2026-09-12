# Analytics ETL

Shared reporting layer for all competitors. It reads completed scraper data from `sandix_price_monitor`, writes reporting snapshots into `sandix_price_analytics`, and provides the views read by Metabase dashboard `Sandix - konkurenti`.

## What Runs When

| Script | Purpose | Run it when |
| --- | --- | --- |
| `analytics_etl.py` | Price comparison KPI, status, and TOP price-gap snapshots | After a completed competitor scraper run |
| `part_number_filter_etl.py` | Part-number classification and coverage snapshot | After a completed competitor scraper run |
| `run_competitor_pipeline.py` | Scraper -> analytics ETL -> filter ETL, sequentially | Preferred command for a new scraper run |
| `setup_metabase_dashboard.py` | Creates or updates dashboard `Sandix - konkurenti` | First setup or dashboard-layout change only |

The ETL uses the newest completed run for the configured competitor:

- `SUCCESS`: all requests completed without technical errors.
- `PARTIAL`: all inputs were processed, but some requests failed. The run is still reported.
- `ABORTED` and `RUNNING`: never used by ETL.

There is no scheduler yet. If the scraper was started manually, wait until it finishes before running the two ETL scripts.

## One-Time Setup

The recommended runtime is the shared scraper environment, which the pipeline wrapper also uses:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
python3 -m venv .venv_scraper
.venv_scraper/bin/pip install -r profibagr-scraper/requirements.txt
```

Create `analytics-etl/.env` from the template and fill PostgreSQL access values:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
cp analytics-etl/.env.example analytics-etl/.env
```

The competitor defaults live in `profibagr-scraper/.env`. Its default is Profibagr. Inline competitor variables in the examples below temporarily override it without changing files.

## Profibagr: Update Reporting After A Manual Scrape

Use this after a manually started Profibagr scraper run has finished:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix/analytics-etl
../.venv_scraper/bin/python analytics_etl.py
../.venv_scraper/bin/python part_number_filter_etl.py
```

The first command writes price comparison reporting. The second command writes filter and coverage reporting. Dashboard `5` reads the refreshed shared views automatically; no separate Metabase refresh is required.

## Bagry ND: Update Reporting After A Manual Scrape

The competitor settings must be passed to both ETL steps. Copy-paste this entire block:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix/analytics-etl
COMPETITOR_CODE=BAGRY_ND COMPETITOR_NAME="Bagry ND" BASE_URL=https://www.jcb-nahradni-dily.cz SEARCH_PATH=/hledani SEARCH_PARAM=query ../.venv_scraper/bin/python analytics_etl.py
COMPETITOR_CODE=BAGRY_ND COMPETITOR_NAME="Bagry ND" BASE_URL=https://www.jcb-nahradni-dily.cz SEARCH_PATH=/hledani SEARCH_PARAM=query ../.venv_scraper/bin/python part_number_filter_etl.py
```

After both commands succeed, dashboard `5` shows Bagry ND in the shared competitor cards alongside Profibagr.

## Profimachinery, Dílybagru, And Strojparts

Website configurations are in `profibagr-scraper/competitors/`. They contain no database credentials and work with the standard `analytics-etl/.env` plus `profibagr-scraper/.env` files.

After a manual scrape, use the matching configuration for both ETL steps. Example for Dílybagru:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix/analytics-etl
COMPETITOR_ENV_FILE="$PWD/../profibagr-scraper/competitors/dilybagru.env.example" ../.venv_scraper/bin/python analytics_etl.py
COMPETITOR_ENV_FILE="$PWD/../profibagr-scraper/competitors/dilybagru.env.example" ../.venv_scraper/bin/python part_number_filter_etl.py
```

Replace `dilybagru.env.example` with one of:

- `profi_machinery.env.example`
- `strojparts.env.example`
- `bagry_nd.env.example`

Pipeline example for Strojparts:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
COMPETITOR_ENV_FILE="$PWD/profibagr-scraper/competitors/strojparts.env.example" .venv_scraper/bin/python analytics-etl/run_competitor_pipeline.py --scope queue
```

Strojparts may return products without a public price. The scraper records those results, but analytics excludes missing or zero competitor prices from price-gap comparisons.

## Preferred: Run The Whole Pipeline

The wrapper stops immediately if a prior stage fails. It avoids running analytics against an unfinished scrape.

Profibagr queue run:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
.venv_scraper/bin/python analytics-etl/run_competitor_pipeline.py --scope queue
```

Profibagr full run:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
.venv_scraper/bin/python analytics-etl/run_competitor_pipeline.py --scope full
```

Bagry ND queue run:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
COMPETITOR_CODE=BAGRY_ND COMPETITOR_NAME="Bagry ND" BASE_URL=https://www.jcb-nahradni-dily.cz SEARCH_PATH=/hledani SEARCH_PARAM=query .venv_scraper/bin/python analytics-etl/run_competitor_pipeline.py --scope queue
```

Other competitors in the background:

Use the competitor configuration file instead of the Profibagr default. This runs scraper, analytics ETL, and filter ETL in that order. The example below is for Bagry ND; replace `bagry_nd.env.example` with `profi_machinery.env.example`, `dilybagru.env.example`, or `strojparts.env.example` as needed.

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
mkdir -p analytics-etl/logs
nohup env COMPETITOR_ENV_FILE="$PWD/profibagr-scraper/competitors/bagry_nd.env.example" .venv_scraper/bin/python analytics-etl/run_competitor_pipeline.py --scope queue > analytics-etl/logs/bagry_nd_pipeline_queue.log 2>&1 &
tail -f analytics-etl/logs/bagry_nd_pipeline_queue.log
```

For a full run, replace `--scope queue` with `--scope full` and use a separate log filename.

If a scraper was already run manually, use the wrapper without launching another scrape:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix
.venv_scraper/bin/python analytics-etl/run_competitor_pipeline.py --skip-scraper
```

For a competitor other than Profibagr, prepend `COMPETITOR_ENV_FILE` with the matching configuration file, as in the background example above.

## Metabase Dashboard

Dashboard provisioning needs these variables in `analytics-etl/.env`:

```dotenv
METABASE_URL=https://your-metabase-host
METABASE_API_KEY=your_api_key
METABASE_DATABASE_ID=your_metabase_database_id
METABASE_COLLECTION_ID=5
METABASE_DASHBOARD_ID=5
```

`METABASE_DATABASE_ID` is Metabase's internal numeric ID of the `sandix_price_analytics` connection. `METABASE_DASHBOARD_ID=5` updates the existing shared dashboard. Leave it empty only when creating or locating a dashboard by name.

Provision or update the shared dashboard:

```bash
cd /tmp/opencode/selenium-lab_JG/Sandix/analytics-etl
../.venv_scraper/bin/python setup_metabase_dashboard.py
```

The dashboard mirrors the Profibagr layout: ORIGINAL KPI, status, price comparison, TOP expensive/cheap; then the alternative block, market-average card `64`, and coverage card `65`. Provisioning is not part of ordinary scraper runs.

## Reporting Outputs

Main shared views used by Metabase:

- `reporting.competitor_latest_batch_v`
- `reporting.competitor_latest_price_comparison_v`
- `reporting.competitor_latest_search_status_v`
- `reporting.competitor_market_price_comparison_v`
- `reporting.part_number_filter_latest_coverage_summary_v`

The market-average card compares products only where multiple competitors have a matching product. It may be empty or not yet meaningful until that intersection grows.

## Part-Number Suffixes

Metabase card `53` (`Filtr part numberů - Sandix originál a očištěná PN`) reads `reporting.part_number_filter_latest_v`. Its `suffixy` and `ocistena_pn` columns are generated by `part_number_filter_etl.py` from the active suffix catalog in `sandix_price_analytics`:

- Source table for adding or disabling suffixes: `reporting.variant_suffix_catalog`
- Read-only active catalog view: `reporting.variant_suffix_catalog_v`
- Seed source: column A of every sheet in `rozliseni_alternativ.xlsx`

The filter ETL imports missing suffixes from the workbook but does not overwrite existing catalog rows. Store manual values in lowercase. To add a suffix or re-enable an existing one, run this in `sandix_price_analytics`:

```sql
INSERT INTO reporting.variant_suffix_catalog (suffix, enabled, source, note)
VALUES ('new-suffix', true, 'manual', 'reason for this suffix')
ON CONFLICT (suffix) DO UPDATE SET
  enabled = true,
  source = EXCLUDED.source,
  note = EXCLUDED.note,
  updated_at = now();
```

To disable a suffix without deleting its audit record:

```sql
UPDATE reporting.variant_suffix_catalog
SET enabled = false, updated_at = now()
WHERE suffix = 'old-suffix';
```

After changing the catalog, run `part_number_filter_etl.py` for a completed competitor run. It rewrites the latest filter snapshot, after which card `53` shows the updated `suffixy` and `ocistena_pn` values.

## Troubleshooting

- `No completed (SUCCESS/PARTIAL) scrape run found`: no reportable run exists for the active `COMPETITOR_CODE`.
- Profibagr data appears after a Bagry ND ETL command: Bagry ND variables were omitted; rerun both ETL commands with the Bagry ND prefix.
- Dashboard does not show a newly scraped competitor: run both ETL scripts for that competitor. Normal dashboard viewing needs no manual refresh.
- A full scraper run can take many hours. Use the background pipeline command and follow its log with `tail -f`.
