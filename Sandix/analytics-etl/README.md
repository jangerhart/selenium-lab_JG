# Analytics ETL

Shared analytic layer for all competitors over `sandix_price_monitor` into `sandix_price_analytics`.

## What it does

- reads the latest successful batch for the configured `COMPETITOR_CODE`
- filters competitor prices to valid values only (`> 0`)
- calculates Sandix vs competitor gaps in Kč and percent
- stores snapshot tables in `sandix_price_analytics.reporting`
- exposes stable `latest` views for Metabase

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Metabase API variables are stored in the same `.env` file and are reused by future scripts via `sandix.metabase`.
`setup_metabase_dashboard.py` also needs `METABASE_DATABASE_ID`.

To switch competitors, set:

```bash
COMPETITOR_CODE=BAGRY_ND
COMPETITOR_NAME=Bagry ND
COMPETITOR_ENV_FILE=/path/to/competitor.env
```

## Run

Build the snapshot:

```bash
python3 analytics_etl.py
```

Build the part-number filter review snapshot:

```bash
python3 part_number_filter_etl.py
```

Bootstrap reporting objects:

```bash
python3 ../pohoda-etl/bootstrap_postgres.py
```

Provision the shared Metabase dashboard:

```bash
python3 setup_metabase_dashboard.py
```

Run the full competitor pipeline:

```bash
python3 run_competitor_pipeline.py --scope queue
```

Background example:

```bash
nohup /tmp/opencode/selenium-lab_JG/Sandix/.venv_scraper/bin/python /tmp/opencode/selenium-lab_JG/Sandix/analytics-etl/run_competitor_pipeline.py --scope queue > /tmp/opencode/selenium-lab_JG/Sandix/profibagr-scraper/logs/pipeline.log 2>&1 &
tail -f /tmp/opencode/selenium-lab_JG/Sandix/profibagr-scraper/logs/pipeline.log
```

## Outputs

- `reporting.competitor_batch_kpi`
- `reporting.competitor_price_comparison`
- `reporting.competitor_search_status`
- `reporting.competitor_latest_batch_v`
- `reporting.competitor_latest_price_comparison_v`
- `reporting.competitor_latest_search_status_v`
- `reporting.competitor_market_price_comparison_v`
- `reporting.part_number_filter_review`
- `reporting.part_number_filter_latest_v`
- `reporting.part_number_filter_latest_summary_v`
- `reporting.part_number_filter_latest_coverage_v`
- `reporting.part_number_filter_latest_coverage_summary_v`
- `reporting.variant_suffix_catalog`
- `reporting.variant_suffix_catalog_v`

The suffix catalog is stored in PostgreSQL and can be reviewed in Metabase.
Standard Metabase dashboards are read-only for this workflow; row edits should be done in PostgreSQL or via a SQL editor with write access.

## Suggested first Metabase page

## KPI

- Products searched
- Matched
- NOT FOUND
- Errors
- Sandix more expensive
- Sandix cheaper
- Average price gap %

## Main table

- Part number
- Product name
- Sandix price
- Avg competitor price
- Gap Kč
- Gap %
- Competitor count

Default sort: `Gap % DESC`

## Useful extras

- TOP 10 - Sandix dražší
- TOP 10 - Sandix levnější
- Search status distribution
