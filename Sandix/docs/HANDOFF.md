# Current project state

Last updated: 2026-08-30

## Current objective

Build a system for automated competitor price monitoring for JCB spare parts.

## Current state

- Sandix is the active Python workspace inside the repo.
- PostgreSQL and Metabase are running.
- `price_scraper_ro` exists and is the scraper read-only role.
- Profibagr PoC scraping works over HTTP without JavaScript.
- Profibagr input filtering currently happens in the scraper query against `search_part_number_normalized`.
- The scraper batch is capped at 100 part numbers.
- `Sandix/docs/DATABASE.md` now contains the target database design.
- `Sandix/docs/DATABASE.md` was trimmed to avoid duplicating project-wide principles from `Sandix/docs/PROJECT_CONTEXT.md`.
- `Sandix/docs/DATABASE.md` was trimmed again to remove project-context-only sections.
- `Sandix/pohoda-etl/` now contains a read-only POHODA snapshot extractor.
- PostgreSQL provisioning account now owns and can write to `sandix_price_monitor` and `sandix_price_analytics`.
- `sandix_price_monitor` and `sandix_price_analytics` now exist and are bootstrapped.
- `Sandix/pohoda-etl/` now bootstraps PostgreSQL schemas/tables/views and writes monitor snapshots.
- `Sandix/pohoda-etl/build_test_analytics.py` now builds a test analytics snapshot from the latest successful Profibagr batch.
- POHODA ETL now writes current snapshots into `sandix_price_monitor` as well as RAW CSV.
- Profibagr scraper now writes scrape runs, search requests and offer observations into `sandix_price_monitor`.
- Final `scraper.scrape_run` state after cleanup: `SUCCESS=1`, `FAILED=1`, `RUNNING=0`.
- Production POHODA import now contains 25,436 rows in `source_pohoda.stock_current` and `core.product`.
- Current eligibility queue in `scraper.v_search_queue` contains 1,412 search identifiers.
- Profibagr full batch against the production queue completed successfully with 100 search identifiers processed.
- Analytics snapshot tables now exist in `sandix_price_analytics.reporting`.

## Files changed

- `AGENTS.md`
- `Sandix/docs/HANDOFF.md`
- `Sandix/docs/PROJECT_CONTEXT.md`
- `Sandix/docs/DATABASE.md`
- `Sandix/pohoda-etl/.env.example`
- `Sandix/pohoda-etl/.gitignore`
- `Sandix/pohoda-etl/README.md`
- `Sandix/pohoda-etl/bootstrap_postgres.py`
- `Sandix/pohoda-etl/pohoda_etl.py`
- `Sandix/pohoda-etl/build_test_analytics.py`
- `Sandix/profibagr-scraper/README.md`
- `Sandix/profibagr-scraper/profibagr_scraper.py`

## Database objects inspected or changed

- Inspected: `scraper.v_profibagr_search_queue`
- Inspected: `search_part_number_normalized`
- Existing objects referenced in this work: `scraper.v_profibagr_input`, `scraper.v_profibagr_search_queue`, `price_scraper_ro`
- Changed in `sandix_price_monitor`: `etl.pohoda_sync_run`, `source_pohoda.stock_current`, `core.product`, `core.own_price_history`, `core.product_identifier`, `scraper.competitor`, `scraper.scrape_run`, `scraper.search_request`, `scraper.search_request_product`, `scraper.offer_observation`
- Changed in `sandix_price_monitor`: `core.product_current_v`, `core.product_search_identifier_v`, `scraper.v_search_queue`, `export.product_current_v`, `export.own_price_history_v`, `export.competitor_offer_history_v`, `export.scrape_run_v`
- Changed in `sandix_price_analytics`: schemas `mart`, `dim`, `fact`, `reporting`

## Tests executed

- `python -m py_compile profibagr_scraper.py`
- `python profibagr_scraper.py`
- row/count check against the filtered queue query
- `python -m py_compile pohoda_etl.py`
- `python pohoda_etl.py --limit 5`
- `python -m py_compile bootstrap_postgres.py pohoda_etl.py`
- `python pohoda_etl.py --limit 5` with PostgreSQL write-back enabled
- PostgreSQL provisioning smoke tests for create privileges and transaction-scoped schema/table creation
- `python -m py_compile profibagr_scraper.py`
- `python profibagr_scraper.py --part-number "32/925895"`
- `python pohoda_etl.py` against production POHODA
- `python profibagr_scraper.py` against the production eligibility queue
- `python -m py_compile build_test_analytics.py bootstrap_postgres.py`
- `python build_test_analytics.py`

## Results

- Batch run succeeded.
- Last successful CSV: `Sandix/profibagr-scraper/data/raw/profibagr/profibagr_20260828_061800.csv`
- Latest batch size: 100 search P/N
- Latest output: 140 CSV rows, 93 OK, 47 NOT_FOUND
- Database design document populated from the provided project specification.
- Database design document now stays focused on schema/model/migration details instead of repeating project-wide principles.
- Database design document is now narrower and keeps only DB-specific invariants plus migration flow.
- POHODA read-only extractor produced a CSV snapshot from the year database.
- Smoke test output: `Sandix/pohoda-etl/data/raw/pohoda/pohoda_20260830_182705.csv`
- PostgreSQL provisioning smoke tests confirmed connect/read access, but schema/table creation failed with insufficient privilege.
- Bootstrap script created schemas, tables and views in `sandix_price_monitor` and schemas in `sandix_price_analytics`.
- POHODA ETL smoke run wrote 5 rows into `source_pohoda.stock_current` and `core.product`, inserted 5 initial `core.own_price_history` rows, then updated the same 5 rows on the next smoke run without duplicating price history.
- `scraper.competitor` now has the `PROFIBAGR` seed row.
- Profibagr scraper smoke run wrote `scraper.scrape_run`, `scraper.search_request` and `scraper.offer_observation` rows for a manual search.
- Old lingering `RUNNING` scrape run was marked `FAILED` during cleanup.
- Current manual smoke search returned offers but no `search_request_product` rows because the chosen part is not eligible under the current queue filter.
- Production POHODA ETL loaded 25,431 source rows and then 5 additional smoke rows from earlier tests now coexist in the monitor DB for a total of 25,436 current rows.
- Profibagr production batch produced `17 OK`, `83 NOT_FOUND`, `0 error` in the latest successful run, with `30` total offers extracted.
- `scraper.search_request_product` currently has 174 rows and `scraper.offer_observation` has 51 rows.
- `sandix_price_analytics.reporting.profibagr_batch_summary` now has one test snapshot row.
- `sandix_price_analytics.reporting.profibagr_price_gap` now has 17 rows for the latest successful batch.
- The first test analytics run surfaced the top price gaps, including several 100 percent gaps where the competitor price was zero.

## Unresolved issues

- `skz_transformed_v` still emits standalone punctuation for some queue rows.
- Its other consumers still need to be understood before changing that view.
- `scraper.v_search_queue` currently uses `ids` as the initial generic search identifier placeholder; legacy transformation logic still needs to be migrated carefully.
- The production-year queue is now populated; earlier empty-queue notes applied only to the previous year database.

## Recommended next step

- Keep Profibagr input filtering isolated from `skz_transformed_v` until downstream consumers are mapped.
- Continue with any database-schema implementation work from `Sandix/docs/DATABASE.md`.
- Keep shared business principles in `Sandix/docs/PROJECT_CONTEXT.md` and DB-specific decisions in `Sandix/docs/DATABASE.md`.
- Keep checking for overlap, but prefer moving general context out of `Sandix/docs/DATABASE.md`.
- Next likely step is to add PostgreSQL load/output for the POHODA ETL once write access and target tables are ready.
- Next blocker to remove: grant the provisioning account CREATE/OWNERSHIP on the target PostgreSQL database or create the DB owned by that account.
- Next step: wire Profibagr scraper to the new monitor export/search queue model, then migrate away from `scraper.v_profibagr_search_queue` only after its consumers are mapped.
- Next step: decide whether `scraper.v_search_queue` should stay empty for this year database or whether the eligibility rule needs adjustment before the next full batch run.
- Next step: inspect the 17 successful requests and decide whether the search identifier transformation needs broader alias coverage for additional Profibagr matches.
- Next step: expose the analytics tables in Metabase and decide whether zero-price competitor rows should be filtered from the price-gap report.
