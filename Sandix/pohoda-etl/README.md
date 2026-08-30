# POHODA ETL

Read-only extractor for POHODA source data that also writes the current snapshot into `sandix_price_monitor`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run

Full snapshot:

```bash
python3 pohoda_etl.py
```

Smoke test with a row limit:

```bash
python3 pohoda_etl.py --limit 5
```

Bootstrap PostgreSQL schemas and tables:

```bash
python3 bootstrap_postgres.py
```

The ETL reads POHODA from `POHODA_DB_*` and writes to `PG_MONITOR_*` if present, otherwise it falls back to the provisioning PostgreSQL account.

## Outputs

- CSV: `data/raw/pohoda/pohoda_YYYYMMDD_HHMMSS.csv`
- log: `logs/pohoda_YYYYMMDD_HHMMSS.log`
