# Sandix

Sandix is the workspace for competitor price monitoring and reporting.

## Main Pieces

- `profibagr-scraper/`: shared competitor scraper
- `analytics-etl/`: shared analytics ETL, filter ETL, and pipeline wrapper
- `docs/`: project context, handoff, and database notes

## Normal Run

Use the wrapper for a full competitor run:

```bash
python3 analytics-etl/run_competitor_pipeline.py --scope queue
```

To switch competitor, set `COMPETITOR_CODE` and `COMPETITOR_NAME` in the environment or `.env` file.

## Development

Run tests:

```bash
python -m unittest discover -s tests
```
