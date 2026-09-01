# Analytics ETL

First usable analytic layer for Profibagr over `sandix_price_monitor` into `sandix_price_analytics`.

## What it does

- reads the latest successful Profibagr batch from `sandix_price_monitor`
- filters competitor prices to valid values only (`> 0`)
- calculates Sandix vs Profibagr gaps in Kč and percent
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

## Outputs

- `reporting.profibagr_batch_kpi`
- `reporting.profibagr_price_comparison`
- `reporting.profibagr_search_status`
- `reporting.profibagr_latest_batch_v`
- `reporting.profibagr_latest_price_comparison_v`
- `reporting.profibagr_latest_search_status_v`
- `reporting.part_number_filter_review`
- `reporting.part_number_filter_latest_v`
- `reporting.part_number_filter_latest_summary_v`
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
- Profibagr price
- Gap Kč
- Gap %
- Offers

Default sort: `Gap % DESC`

## Useful extras

- TOP 10 - Sandix dražší
- TOP 10 - Sandix levnější
- Search status distribution
