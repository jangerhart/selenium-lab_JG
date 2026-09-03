# Current project state

Last updated: 2026-09-03

## Current objective

Build a filtering-first system for automated competitor price monitoring for JCB spare parts.

## Current state

- Sandix is the active Python workspace inside the repo.
- PostgreSQL and Metabase are running.
- `price_scraper_ro` exists and is the scraper read-only role.
- Profibagr PoC scraping works over HTTP without JavaScript.
- Profibagr input filtering currently happens in the scraper query against `search_part_number_normalized`.
- The scraper batch is capped at 500 part numbers.
- `Sandix/docs/DATABASE.md` now contains the target database design.
- `Sandix/docs/DATABASE.md` was trimmed to avoid duplicating project-wide principles from `Sandix/docs/PROJECT_CONTEXT.md`.
- `Sandix/docs/DATABASE.md` was trimmed again to remove project-context-only sections.
- `Sandix/pohoda-etl/` now contains a read-only POHODA snapshot extractor.
- PostgreSQL provisioning account now owns and can write to `sandix_price_monitor` and `sandix_price_analytics`.
- `sandix_price_monitor` and `sandix_price_analytics` now exist and are bootstrapped.
- `Sandix/pohoda-etl/` now bootstraps PostgreSQL schemas/tables/views and writes monitor snapshots.
- `Sandix/analytics-etl/` now contains the first usable Profibagr analytics ETL, plus a separate part-number filter ETL for original/alternative classification review.
- Suffixes now live in `sandix_price_analytics.reporting.variant_suffix_catalog`; Excel is only the initial seed source.
- `Sandix/pohoda-etl/build_test_analytics.py` is now a compatibility wrapper to the new analytics ETL.
- Metabase now has a first Sandix dashboard in collection `Sandix` with ID `2`, localized to Czech titles/descriptions, and cards for KPI, search status, price comparison, overpriced and underpriced items.
- Metabase now also has `Sandix - filtr part numberů` in collection `Sandix` with ID `3` for filter review, with cards `52` and `53`.
- Metabase card `54` now shows the editable suffix catalog review table sorted by suffix length.
- Card `52` is now named `Filtr part numberů - souhrn originálů a alternativ`.
- Card `53` is now named `Filtr part numberů - alternativy a výjimky`.
- Part-number suffix parsing now comes from `reporting.variant_suffix_catalog` (seeded from `rozliseni_alternativ.xlsx`), splits comma/semicolon-separated suffixes, and strips by descending suffix length.
- Metabase dashboard `Sandix - Profibagr analytika` now also contains a second block of cards for the alternative-vs-alternative scope.
- Metabase dashboard `Sandix - Profibagr analytika` is now set to `width=full` and the cards are stacked in a single full-width column to minimize horizontal scrolling.
- Metabase dashboard `Sandix - Profibagr analytika` was briefly broken by invalid SQL aliases, then repaired by quoting the `%` aliases and fixing the search-status sort expression.
- Metabase card `43` was simplified to two columns (`stav_hledani`, `pocet_dotazu`) so the bar chart no longer asks for X/Y axes.
- Metabase card `44` now includes `odkaz_na_profibagr` and the analytics snapshot stores the best valid competitor product URL.
- Metabase API connection variables are stored locally in `Sandix/analytics-etl/.env` and are exposed for future scripts via `sandix.metabase`.
- POHODA ETL now writes current snapshots into `sandix_price_monitor` as well as RAW CSV.
- Profibagr scraper now writes scrape runs, search requests and offer observations into `sandix_price_monitor`.
- Final `scraper.scrape_run` state after cleanup: `SUCCESS=1`, `FAILED=1`, `RUNNING=0`.
- Production POHODA import now contains 25,436 rows in `source_pohoda.stock_current` and `core.product`.
- Current eligibility queue in `scraper.v_search_queue` contains 1,412 search identifiers.
- Profibagr full batch against the production queue completed successfully with 500 search identifiers processed.
- First usable analytics snapshot tables and latest views now exist in `sandix_price_analytics.reporting`.

## Files changed

- `AGENTS.md`
- `Sandix/docs/HANDOFF.md`
- `Sandix/docs/PROJECT_CONTEXT.md`
- `Sandix/docs/DATABASE.md`
- `Sandix/analytics-etl/.env.example`
- `Sandix/analytics-etl/.env`
- `Sandix/analytics-etl/part_number_filter_etl.py`
- `Sandix/analytics-etl/.gitignore`
- `Sandix/analytics-etl/README.md`
- `Sandix/analytics-etl/analytics_etl.py`
- `Sandix/analytics-etl/requirements.txt`
- `Sandix/pohoda-etl/.env.example`
- `Sandix/pohoda-etl/.gitignore`
- `Sandix/pohoda-etl/README.md`
- `Sandix/pohoda-etl/bootstrap_postgres.py`
- `Sandix/pohoda-etl/build_test_analytics.py`
- `Sandix/pohoda-etl/pohoda_etl.py`
- `Sandix/profibagr-scraper/README.md`
- `Sandix/profibagr-scraper/profibagr_scraper.py`
- `Sandix/sitecustomize.py`
- `Sandix/src/sandix/analytics.py`
- `Sandix/src/sandix/part_numbers.py`
- `Sandix/tests/__init__.py`
- `Sandix/tests/test_analytics.py`
- `Sandix/tests/test_part_numbers.py`
- `Sandix/tests/test_version.py`

## Database objects inspected or changed

- Inspected: `scraper.v_profibagr_search_queue`
- Inspected: `search_part_number_normalized`
- Existing objects referenced in this work: `scraper.v_profibagr_input`, `scraper.v_profibagr_search_queue`, `price_scraper_ro`
- Changed in `sandix_price_monitor`: `etl.pohoda_sync_run`, `source_pohoda.stock_current`, `core.product`, `core.own_price_history`, `core.product_identifier`, `scraper.competitor`, `scraper.scrape_run`, `scraper.search_request`, `scraper.search_request_product`, `scraper.offer_observation`
- Changed in `sandix_price_monitor`: `core.product_current_v`, `core.product_search_identifier_v`, `scraper.v_search_queue`, `export.product_current_v`, `export.own_price_history_v`, `export.competitor_offer_history_v`, `export.scrape_run_v`
- Changed in `sandix_price_analytics`: schemas `mart`, `dim`, `fact`, `reporting`; new reporting objects `reporting.profibagr_batch_kpi`, `reporting.profibagr_price_comparison`, `reporting.profibagr_search_status`, `reporting.profibagr_latest_batch_v`, `reporting.profibagr_latest_price_comparison_v`, `reporting.profibagr_latest_overpriced_v`, `reporting.profibagr_latest_underpriced_v`, `reporting.profibagr_latest_search_status_v`

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
- `python -m py_compile analytics-etl/analytics_etl.py pohoda-etl/bootstrap_postgres.py pohoda-etl/build_test_analytics.py src/sandix/analytics.py tests/test_analytics.py`
- `python -m unittest discover -s tests`
- `python -m py_compile analytics-etl/part_number_filter_etl.py src/sandix/part_numbers.py tests/test_part_numbers.py`
- `python -m unittest discover -s tests`
- `python analytics-etl/part_number_filter_etl.py` against the production queue for filter review
- `python analytics-etl/part_number_filter_etl.py` now seeds and reads suffixes from `reporting.variant_suffix_catalog`
- `python analytics-etl/analytics_etl.py` against the production queue, twice to verify idempotence
- `python analytics-etl/analytics_etl.py` with dual original/alternative reporting enabled
- Metabase query checks via `POST /api/agent/v1/question/{id}/query` for cards `42` to `46`
- Metabase query check for card `44` confirms the Profibagr URL column is returned and populated.

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
- `sandix_price_analytics.reporting.profibagr_batch_kpi` has one snapshot row for the latest Profibagr batch.
- `sandix_price_analytics.reporting.profibagr_price_comparison` has 15 rows for the latest successful batch.
- `sandix_price_analytics.reporting.profibagr_search_status` has 3 rows (`OK`, `NOT_FOUND`, `ERROR`).
- Latest batch summary: `100` searched, `17 OK`, `83 NOT_FOUND`, `0 ERROR`, `30` raw offers, `25` valid offers, `5` excluded invalid offers, `15` matched products.
- No invalid competitor price (`<= 0`) is used in the latest comparison view.
- The repeated analytics run stayed idempotent: snapshot counts remained `1 / 15 / 3`.
- Dual analytics ETL succeeded for the latest batch: `ORIGINAL` produced `7` matched products and `ALTERNATIVE` produced `0` matched products from the same scrape run.
- Part-number filter ETL succeeded with `15,491` Sandix original tokens, `19,801` Sandix alternative tokens, `20` alternative Profibagr observations, and `8` unresolved competitor observations in the review snapshot.
- Part-number filter ETL was regenerated after switching suffix parsing to Excel-first-column input.
- Part-number filter ETL rerun after the manual suffix expansion produced `13,613` Sandix original tokens, `21,679` Sandix alternative tokens, `32` original Profibagr observations, `90` alternative Profibagr observations, and `8` unresolved competitor observations.
- Part-number suffix catalog currently contains `166` enabled suffixes and is sorted by length descending for ETL use.
- Part-number normalization now preserves `/` in both original and cleaned PN fields, and the POHODA search-identifier view uses the same rule.
- Profibagr scraper now deduplicates queue items after suffix stripping, so entries like `02/100284AB`, `02/100284AD`, and `02/100284AH` collapse to one `02/100284`.
- Latest Profibagr scrape run started with `INPUT COUNT: 447` after suffix-base dedupe and completed successfully.
- Profibagr scraper now writes `last_heartbeat_at` and `last_progress` into `scraper.scrape_run`, aborts stale `RUNNING` runs on startup, and finalizes `SIGTERM`/`SIGINT` as `ABORTED`.
- Latest Profibagr scrape run `c2165267-c2e0-4ef9-8472-4c232fe9fa3f` completed with `37` successful requests, `36` matched products, `45` raw offers, `43` valid offers, `1` excluded offer, and `380` total offers.
- Metabase cards `42`, `52`, `53`, and `54` now query the refreshed latest views successfully.
- Profibagr product pages that contain `Original` are now classified as `ORIGINAL`; current filter snapshot shows `10` `BASE_MATCH` rows and `7` `TEXT_ORIGINAL` rows for Profibagr observations.
- Metabase dashboard `Sandix - filtr part numberů` now contains cards `52` and `53` for filter review.
- Card `53` is now `Filtr part numberů - Sandix originál a očištěná PN` and shows only `SANDIX / SOURCE_TOKEN` rows from the POHODA ETL snapshot.
- Metabase dashboard `Sandix - Profibagr analytika` now includes cards `47` to `51` for the alternative scope.
- TOP overpriced products are now visible in `reporting.profibagr_latest_overpriced_v`; TOP underpriced products are in `reporting.profibagr_latest_underpriced_v`.
- Metabase dashboard `Sandix Profibagr Analytics` now contains cards `42` to `46` and is ready for first review.
- Metabase dashboard is now named `Sandix - Profibagr analytika` and the question titles/descriptions are in Czech.
- Dashboard layout is now full-width with a single vertical stack of full-width cards.
- All five Metabase cards now execute successfully again and the dashboard is usable.
- The comparison table now exposes the Profibagr product URL as a clickable-looking string column.
- Profibagr replacement detection is still weak; alternative matching needs separate manual analysis.

## Unresolved issues

- `skz_transformed_v` still emits standalone punctuation for some queue rows.
- Its other consumers still need to be understood before changing that view.
- `scraper.v_search_queue` currently uses `ids` as the initial generic search identifier placeholder; legacy transformation logic still needs to be migrated carefully.
- The legacy PoC analytics tables `reporting.profibagr_batch_summary` and `reporting.profibagr_price_gap` still exist; the new ETL does not use them.
- Profibagr replacement detection still needs investigation before treating `ALTERNATIVE` classification as trustworthy.

## Recommended next step

- Keep Profibagr input filtering isolated from `skz_transformed_v` until downstream consumers are mapped.
- Continue with any database-schema implementation work from `Sandix/docs/DATABASE.md`.
- Keep shared business principles in `Sandix/docs/PROJECT_CONTEXT.md` and DB-specific decisions in `Sandix/docs/DATABASE.md`.
- Keep checking for overlap, but prefer moving general context out of `Sandix/docs/DATABASE.md`.
- Next step: create the first Metabase dashboard / questions directly on `reporting.profibagr_latest_batch_v`, `reporting.profibagr_latest_price_comparison_v`, and `reporting.profibagr_latest_search_status_v`.
- Next step: review the Metabase dashboard and decide whether to keep the current layout or add a date/status filter.
- Next step: decide when to retire the legacy PoC analytics tables once the new views are accepted.
- Next step: consider whether rows with no valid competitor price should be surfaced separately as diagnostics instead of being excluded from comparison.
