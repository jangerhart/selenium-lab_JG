# Current project state

Last updated: 2026-08-28

## Current objective

Build a system for automated competitor price monitoring for JCB spare parts.

## Current state

- Sandix is the active Python workspace inside the repo.
- PostgreSQL and Metabase are running.
- `price_scraper_ro` exists and is the scraper read-only role.
- Profibagr PoC scraping works over HTTP without JavaScript.
- Profibagr input filtering currently happens in the scraper query against `search_part_number_normalized`.
- The scraper batch is capped at 100 part numbers.

## Files changed

- `AGENTS.md`
- `docs/HANDOFF.md`
- `docs/PROJECT_CONTEXT.md`

## Database objects inspected or changed

- Inspected: `scraper.v_profibagr_search_queue`
- Inspected: `search_part_number_normalized`
- Existing objects referenced in this work: `scraper.v_profibagr_input`, `scraper.v_profibagr_search_queue`, `price_scraper_ro`

## Tests executed

- `python -m py_compile profibagr_scraper.py`
- `python profibagr_scraper.py`
- row/count check against the filtered queue query

## Results

- Batch run succeeded.
- Last successful CSV: `data/raw/profibagr/profibagr_20260828_061800.csv`
- Latest batch size: 100 search P/N
- Latest output: 140 CSV rows, 93 OK, 47 NOT_FOUND

## Unresolved issues

- `skz_transformed_v` still emits standalone punctuation for some queue rows.
- Its other consumers still need to be understood before changing that view.

## Recommended next step

- Keep Profibagr input filtering isolated from `skz_transformed_v` until downstream consumers are mapped.
