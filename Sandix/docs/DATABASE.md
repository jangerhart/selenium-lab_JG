# Sandix Price Monitor - Database Design

## 1. Purpose

This document defines the target database architecture and data model for the Sandix Price Monitor project.

It focuses on:

* source data imported from POHODA / Microsoft SQL Server
* operational product data
* Sandix own-price history
* competitor scraping runs
* competitor search requests
* raw competitor offer observations
* interfaces between ETL, scrapers and future analytics
* migration from existing experimental PostgreSQL objects

This document intentionally does **not** define the final analytical model used by Metabase.

The analytical database will be designed later, after multiple competitor price sources are available and the pricing-comparison requirements are sufficiently understood.

Project-wide business and scraper principles live in `PROJECT_CONTEXT.md`; this file focuses on database design, schema layout and migration.

---

# 2. System boundaries

The solution consists of several physically separated components.

```text id="0flj5c"
                  PRODUCTION ENVIRONMENT

             POHODA / MS SQL Express
                 SOURCE OF TRUTH
                       │
                       │ TCP / read-only
                       ▼
              Linux ETL / Scraper host
               ┌───────┴────────┐
               │                │
          POHODA ETL       Web scrapers
               │                │
               └───────┬────────┘
                       ▼
             PostgreSQL PaaS / Virtuoso

             sandix_price_monitor
                       │
                       │ analytics ETL
                       ▼
             PostgreSQL PaaS / Virtuoso

             sandix_price_analytics
                       │
                       │ read-only
                       ▼
                  Metabase PaaS
```

The PostgreSQL engine is provided as a Virtuoso PaaS service and is operating-system isolated from the scraper host and Metabase container.

Metabase can communicate with PostgreSQL using private PaaS networking.

---

# 3. Database responsibilities

Three logically different databases exist or are expected to exist.

## 3.1 POHODA production database

Technology:

```text id="k9qdsu"
Microsoft SQL Server Express
```

Role:

```text id="8dr1zv"
authoritative source of Sandix product data
```

POHODA remains the source of truth for:

* product identity
* current IDS
* product name
* stock quantity
* available quantity
* purchase price
* selling price
* e-shop availability flag

Sandix Price Monitor must never write to the POHODA database.

Access from ETL is read-only.

---

## 3.2 Operational Price Monitor database

Proposed database name:

```text id="4u45qn"
sandix_price_monitor
```

Technology:

```text id="cmbp4e"
PostgreSQL
```

Responsibilities:

* synchronized POHODA product state
* stable internal product identity
* Sandix price history
* search identifiers
* scraper configuration
* scraper runs
* competitor search history
* competitor raw offer observations
* operational scraper data contracts
* export interface for future analytics

This is the main operational database of the application.

---

## 3.3 Analytical database

Proposed database name:

```text id="sv80bt"
sandix_price_analytics
```

Responsibilities:

* analytical transformation
* cross-competitor price comparison
* historical market analysis
* reference-price calculation
* pricing recommendations
* Metabase datasets

The final schema of this database is intentionally deferred.

Metabase should primarily read from this analytical database rather than directly from operational scraper tables.

---

# 4. Metabase internal database

The Metabase application also has its own internal application database.

This contains Metabase-specific objects such as:

* users
* dashboards
* questions
* metadata
* configuration

This database is not part of the Sandix analytical data model.

Do not store scraped price data in the Metabase application database.

---

# 5. Operational database schemas

The target `sandix_price_monitor` database should use explicit PostgreSQL schemas.

Recommended schemas:

```text id="k8n06y"
source_pohoda
core
etl
scraper
export
legacy
```

The `public` schema should not be used for new application objects.

---

# 6. Schema responsibilities

## source_pohoda

Contains the latest synchronized representation of selected POHODA data.

Purpose:

```text id="5mmqbb"
What does POHODA say right now?
```

Data in this schema is controlled exclusively by the POHODA ETL.

---

## core

Contains application-level identity and Sandix-owned historical/master data.

Purpose:

```text id="p9ebur"
What does Price Monitor know about Sandix products?
```

Examples:

* stable internal product IDs
* source-product mappings
* own price history
* product search identifiers
* future historical/alternative part numbers

---

## etl

Contains technical metadata about synchronization jobs.

Examples:

* POHODA synchronization runs
* ETL status
* counts
* errors
* source database identity

---

## scraper

Contains competitor scraping configuration and operational history.

Examples:

* competitors
* scraper runs
* search requests
* search-to-product mappings
* competitor offer observations

---

## export

Contains stable PostgreSQL views intended for downstream analytics ETL.

Analytics should consume this contract rather than depend directly on the physical implementation of operational tables.

---

## legacy

Contains obsolete objects retained temporarily during migration.

No new application development should depend on `legacy`.

---

# 7. Naming conventions

Use:

```text id="q5a20w"
lowercase_snake_case
```

for database, schema, table, view and column names.

Examples:

```text id="goxll2"
product_id
available_quantity
price_without_vat
observed_at
```

Views should preferably end with:

```text id="q05p4m"
_v
```

Materialized views:

```text id="i3jwo6"
_mv
```

Historical tables should use descriptive names such as:

```text id="wepr9j"
own_price_history
offer_observation
```

Avoid Czech database identifiers in the new model.

The mapping to original POHODA fields is documented explicitly.

---

# 8. Common data types

Recommended PostgreSQL types:

## IDs

Application entity IDs:

```text id="2i4d3q"
bigint generated always as identity
```

Scraper/ETL execution IDs:

```text id="3a61pc"
uuid
```

UUIDs may be generated by Python.

---

## Money

Use:

```text id="ggf0k5"
numeric(18,4)
```

Never use floating-point types for prices.

---

## Quantity

Use:

```text id="q0m2y2"
numeric(18,6)
```

This supports units other than integer pieces.

---

## Currency

Use ISO 4217 codes:

```text id="qd6r12"
char(3)
```

Examples:

```text id="11klvx"
CZK
EUR
PLN
USD
GBP
```

---

## Time

Operational timestamps should use:

```text id="rwkyn1"
timestamp with time zone
```

Application and scraper timestamps should preferably be stored in UTC.

Source timestamps originating directly from POHODA may additionally be preserved separately.

---

# 9. POHODA source fields

The first ETL version requires the following source fields from `dbo.SKz`.

| POHODA        | Price Monitor meaning             |
| ------------- | --------------------------------- |
| `ID`          | source technical product ID       |
| `IDS`         | current Sandix/product identifier |
| `Nazev`       | product name                      |
| `StavZ`       | physical/current stock quantity   |
| `VPrDispMnoz` | available quantity                |
| `IObchod`     | enabled for internet shop         |
| `NakupC`      | purchase price without VAT        |
| `NakupDPH`    | purchase price including VAT      |
| `ProdejKc`    | selling price without VAT         |
| `ProdejDPH`   | selling price including VAT       |
| `CMKodNC`     | purchase currency                 |
| `CMKodPC`     | selling currency                  |
| `DatSave`     | source record save timestamp      |

Additional fields may be added later if business requirements require them.

The ETL should not replicate the complete `SKz` table unless a concrete use case requires it.

---

# 10. Stock semantics

Two stock-related values are intentionally retained.

```text id="jtvfsy"
stock_quantity
```

maps to:

```text id="gldhgu"
SKz.StavZ
```

and represents the current stock quantity.

```text id="vla0gs"
available_quantity
```

maps to:

```text id="h6qncw"
SKz.VPrDispMnoz
```

and represents currently available quantity.

During analysis of the supplied POHODA export, `VPrDispMnoz` behaved as:

```text id="kx3uii"
StavZ - ObjedP
```

for the inspected populated records.

The Price Monitor therefore treats `VPrDispMnoz` as the more appropriate field for determining whether stock is currently available for competitor-price monitoring.

The original `StavZ` value is nevertheless preserved.

---

# 12. POHODA ETL architecture

The POHODA ETL is a standalone application component.

It must be independent from all competitor scrapers.

Conceptual flow:

```text id="fki25v"
POHODA MSSQL
     │
     │ SELECT
     ▼
pohoda_etl
     │
     ▼
source_pohoda
     │
     ├── core identity/history
     │
     └── scraper input
```

Competitor scrapers must not connect directly to POHODA.

---

# 13. POHODA synchronization strategy

The current POHODA dataset contains approximately 8,000 products.

This volume is small.

The initial ETL should therefore use a simple full synchronization rather than implementing:

* Change Data Capture
* triggers
* complicated incremental synchronization
* SQL Server Change Tracking

Recommended initial frequency:

```text id="08f5pn"
once per day
```

A full read of approximately 8,000 rows is operationally negligible.

---

# 14. ETL run table

Recommended table:

```text id="6sn7je"
etl.pohoda_sync_run
```

Columns:

```text id="y1nbj3"
sync_run_id          uuid primary key
started_at           timestamptz not null
finished_at          timestamptz
status               text not null
source_server        text
source_database      text
rows_read            integer
rows_inserted        integer
rows_updated         integer
price_changes        integer
error_count          integer
error_message        text
```

Suggested statuses:

```text id="t3nfmo"
RUNNING
SUCCESS
FAILED
PARTIAL
```

Each synchronized source record should be traceable to a synchronization run.

---

# 15. Current POHODA product state

Recommended table:

```text id="a5apls"
source_pohoda.stock_current
```

Columns:

```text id="spwfav"
pohoda_id                 bigint not null
source_database           text not null

ids                       text
product_name              text

stock_quantity            numeric(18,6)
available_quantity        numeric(18,6)
web_enabled               boolean

purchase_price_net        numeric(18,4)
purchase_price_gross      numeric(18,4)
purchase_currency         char(3)

selling_price_net         numeric(18,4)
selling_price_gross       numeric(18,4)
selling_currency          char(3)

source_saved_at           timestamp
extracted_at              timestamptz not null
last_sync_run_id          uuid not null
```

Recommended key:

```text id="tug10p"
(source_database, pohoda_id)
```

Reason:

`SKz.ID` is considered stable inside the current POHODA source database, but behavior during accounting-database/year migration has not yet been confirmed.

Including `source_database` prevents accidental identity collision.

---

# 16. Internal product identity

Do not use `IDS` as the primary key of a product.

Part numbers can change.

A product may also have:

* current P/N
* historical P/N
* alternative P/N
* internal Sandix code
* supplier identifier

Recommended table:

```text id="yktddt"
core.product
```

Columns:

```text id="ui17er"
product_id            bigint generated always as identity primary key

source_database       text
pohoda_id             bigint

created_at            timestamptz not null
retired_at            timestamptz
```

Recommended uniqueness for the initial implementation:

```text id="qs5mac"
unique(source_database, pohoda_id)
```

The application's `product_id` becomes the stable Price Monitor identity.

---

# 17. Product current view

Avoid copying current POHODA attributes unnecessarily into `core.product`.

Instead expose a view:

```text id="yqm666"
core.product_current_v
```

Conceptually:

```text id="6r265z"
core.product
    JOIN
source_pohoda.stock_current
```

The view should expose:

```text id="o4e1av"
product_id
pohoda_id
ids
product_name
stock_quantity
available_quantity
web_enabled
purchase_price_net
purchase_price_gross
purchase_currency
selling_price_net
selling_price_gross
selling_currency
source_saved_at
```

This keeps source-state ownership clear.

---

# 18. Sandix own-price history

Own Sandix prices must be historized.

Reason:

Price changes will be performed manually based on analytics.

Historical comparison must later answer questions such as:

```text id="49yr0p"
What was our selling price when the competitor price was X?
When did our price change?
Did the expected change actually happen?
```

Recommended table:

```text id="f9iw6i"
core.own_price_history
```

Columns:

```text id="fop863"
own_price_history_id     bigint generated always as identity primary key
product_id               bigint not null

valid_from               timestamptz not null

purchase_price_net       numeric(18,4)
purchase_price_gross     numeric(18,4)
purchase_currency        char(3)

selling_price_net        numeric(18,4)
selling_price_gross      numeric(18,4)
selling_currency         char(3)

sync_run_id              uuid not null
```

Foreign key:

```text id="bbvnfd"
product_id → core.product.product_id
```

---

# 19. Own-price history rule

Do not insert identical price snapshots every day.

During POHODA synchronization:

```text id="fnkns6"
compare current prices
with latest historical price
```

If prices are unchanged:

```text id="i79xx5"
do nothing
```

If any monitored price changes:

```text id="cvr0kq"
insert new history row
```

This provides complete price history without unnecessary duplication.

Do not overwrite historical price records.

---

# 20. Product identifiers

Future model:

```text id="nklc4k"
core.product_identifier
```

This table is architecturally expected but is not mandatory for the first Profibagr production version.

Purpose:

* current part numbers
* historical part numbers
* alternative part numbers
* Sandix internal identifiers
* OEM identifiers
* supplier identifiers

Suggested future columns:

```text id="zrkumy"
product_identifier_id
product_id
identifier
identifier_normalized
identifier_type
manufacturer
is_primary
valid_from
valid_to
created_at
```

Possible identifier types:

```text id="xfv05m"
CURRENT
HISTORICAL
ALTERNATIVE
SANDIX_INTERNAL
OEM
SUPPLIER
```

Management of these mappings may later be implemented using a simple dedicated web application.

This feature is currently backlog.

---

# 23. Competitor definition

Recommended table:

```text id="twl2ud"
scraper.competitor
```

Columns:

```text id="of07gp"
competitor_id          bigint generated always as identity primary key
competitor_code        text unique not null
competitor_name        text not null
base_url               text
default_currency       char(3)
enabled                boolean not null default true
created_at             timestamptz not null
```

Example:

```text id="83fr86"
PROFIBAGR
Profibagr
https://www.profibagr.cz
CZK
true
```

Competitor identity must not be encoded only in scraper source code.

---

# 24. Scraper runs

Every scraper execution must have an explicit run record.

Recommended table:

```text id="7odf5p"
scraper.scrape_run
```

Columns:

```text id="gx1hi8"
run_id                    uuid primary key
competitor_id             bigint not null

started_at                timestamptz not null
finished_at               timestamptz

status                    text not null

queue_count               integer
search_success_count      integer
not_found_count           integer
error_count               integer
offer_count               integer

raw_file_path             text
raw_file_sha256           text

scraper_version           text
error_message             text
```

Suggested statuses:

```text id="l6fubp"
RUNNING
SUCCESS
PARTIAL
FAILED
```

Foreign key:

```text id="exzr3z"
competitor_id → scraper.competitor
```

---

# 25. Search queue

HTTP requests should be deduplicated before scraping.

Several Sandix products may resolve to the same competitor-search identifier.

Conceptually:

```text id="63325h"
Sandix product A ─┐
Sandix product B ─┼─→ 400/F0341 → one HTTP request
Sandix product C ─┘
```

A generic queue view should eventually exist.

Example:

```text id="1ps84e"
scraper.v_search_queue
```

Possible output:

```text id="dxd58k"
competitor_id
search_identifier
search_identifier_normalized
```

Competitor-specific queue views may exist when a particular shop requires special behavior.

---

# 26. Search request history

A competitor search is not the same thing as an offer observation.

A successful search may return:

```text id="v8e0kd"
0 offers
1 offer
multiple offers
```

Therefore store search execution independently.

Recommended table:

```text id="3d3ksn"
scraper.search_request
```

Columns:

```text id="syy9hc"
search_request_id          bigint generated always as identity primary key
run_id                     uuid not null

searched_identifier        text not null
searched_identifier_norm   text

requested_at               timestamptz
completed_at               timestamptz

status                     text not null
match_count                integer

http_status                integer
error_type                 text
error_message              text
```

Foreign key:

```text id="y78ze4"
run_id → scraper.scrape_run
```

Suggested statuses:

```text id="q4e3cv"
OK
NOT_FOUND
HTTP_ERROR
PARSER_ERROR
TIMEOUT
BLOCKED
UNEXPECTED_RESPONSE
```

`NOT_FOUND` is a valid search result, not a scraper failure.

---

# 27. Search request to Sandix product mapping

Because one deduplicated HTTP request may represent multiple Sandix products, use a many-to-many mapping.

Recommended table:

```text id="bd3vb8"
scraper.search_request_product
```

Columns:

```text id="e4whdy"
search_request_id
product_id
source_identifier
```

Primary key:

```text id="q7nmd2"
(search_request_id, product_id)
```

Foreign keys:

```text id="g3yh0f"
search_request_id → scraper.search_request
product_id        → core.product
```

This preserves the historical mapping that existed when the scrape occurred.

It avoids depending on future identifier transformations during historical analysis.

---

# 28. Competitor offer observations

Every individual competitor offer returned by a search should be stored independently.

Recommended table:

```text id="c84s44"
scraper.offer_observation
```

Columns:

```text id="qft1ur"
observation_id            bigint generated always as identity primary key

search_request_id         bigint not null

found_identifier          text
found_identifier_norm     text

competitor_product_name   text

price_without_vat         numeric(18,4)
price_with_vat            numeric(18,4)
currency                  char(3)

availability_raw          text
product_url               text

observed_at               timestamptz not null

match_type                text
match_confidence          numeric(5,4)
```

Foreign key:

```text id="0tdyb4"
search_request_id → scraper.search_request
```

---

# 29. Observation rules

Offer observations are append-only historical facts.

A later scrape must not update the price of an earlier observation.

Example:

```text id="1fhcgm"
2026-08-28 | PROFIBAGR | 980/88215-A | 1341 CZK
2026-08-29 | PROFIBAGR | 980/88215-A | 1390 CZK
```

Both records remain stored.

---

# 30. Multiple offers

A competitor search may return multiple potentially relevant products.

Example:

```text id="h4mzbj"
search: 980/88215

offer 1:
980/88215-A

offer 2:
980/88215-A1
```

Both must be stored as separate observations.

The operational scraper layer must not automatically reduce multiple offers to:

```text id="5u7dxp"
the first result
the cheapest result
the most expensive result
```

The future analytical layer will determine how observations participate in pricing decisions.

---

# 31. Multi-currency support

Operational competitor data must be stored in the currency in which it was observed.

Example:

```text id="mwo1q7"
price_without_vat = 31.50
currency = EUR
```

Do not convert competitor prices to CZK inside scraper code.

Currency conversion belongs to future analytics.

The data model must support additional ISO 4217 currencies without schema changes.

---

# 32. Raw CSV archive

RAW scraper CSV files remain outside PostgreSQL.

Recommended filesystem structure:

```text id="v7z5db"
data/
└── raw/
    ├── profibagr/
    ├── competitor_2/
    └── competitor_3/
```

RAW data is an audit and recovery layer.

PostgreSQL stores normalized operational history.

The corresponding path should be recorded in:

```text id="9dsk26"
scraper.scrape_run.raw_file_path
```

Optionally also store:

```text id="qnz187"
SHA-256
```

to detect accidental file modification.

---

# 33. Retention

Price history is retained indefinitely.

This applies to:

```text id="wxpmlk"
core.own_price_history
scraper.search_request
scraper.search_request_product
scraper.offer_observation
scraper.scrape_run
```

No automatic historical deletion is currently required.

At the expected data volume, long-term detailed retention is acceptable.

---

# 34. Analytics interface

The final analytical database design is deferred.

The operational database should nevertheless expose a stable interface through:

```text id="byicr4"
export
```

Possible future views:

```text id="klzpg0"
export.product_current_v
export.own_price_history_v
export.competitor_offer_history_v
export.scrape_run_v
```

The analytics ETL should preferably read from these views rather than depend directly on internal operational tables.

---

# 35. Analytical database expectations

The future:

```text id="f5dhsq"
sandix_price_analytics
```

must support simultaneous comparison of multiple competitor price lists.

Conceptually:

```text id="7qq9tx"
                  Sandix product
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
      Profibagr    Competitor B   Competitor C
          │             │             │
          └─────────────┼─────────────┘
                        ▼
                analytical model
                        │
                        ▼
                  price decision
```

The analytical layer may later implement:

* current competitor prices
* historical competitor prices
* lowest relevant price
* average price
* median price
* weighted competitor price
* configurable tolerance
* pricing status
* own-price history comparison

No such business logic belongs in `scraper.offer_observation`.

---

# 36. Metabase access

Metabase should use a dedicated read-only PostgreSQL account against:

```text id="pqow2e"
sandix_price_analytics
```

Metabase should not require write permissions to operational Price Monitor data.

Direct Metabase dependency on:

```text id="434jwj"
source_pohoda
core
scraper
```

should be avoided once the analytical database is available.

---

# 37. Database roles

Target roles should be separated by responsibility.

## POHODA ETL role

Operational PostgreSQL permissions:

```text id="h4j4aw"
write: source_pohoda
write: etl
controlled write: core
read: required core objects
```

MSSQL permissions:

```text id="7mnb5h"
SELECT only
```

---

## Scraper diagnostic role

Current role:

```text id="ay8zcx"
price_scraper_ro
```

Purpose:

* development
* diagnostics
* queue inspection

Permissions:

```text id="hudq52"
SELECT only
```

---

## Future scraper application role

A separate production scraper role should eventually be created.

It will need:

```text id="noe6d3"
SELECT
    scraper queue views
    required core views

INSERT
    scrape_run
    search_request
    search_request_product
    offer_observation
```

Do not simply broaden `price_scraper_ro`.

Keep the diagnostic read-only account separate.

---

## Analytics ETL role

The future analytics loader should receive:

```text id="3reg6v"
SELECT on export.*
```

and write permissions only in:

```text id="88d6e3"
sandix_price_analytics
```

---

## Metabase role

```text id="co0gel"
SELECT only
```

against the analytical database.

---

# 38. Current legacy objects

The existing PostgreSQL database contains objects created during previous experiments.

Known objects include:

```text id="5ptnxk"
public.skz
public.skz_transformed_v
public.jcb_prod
public.jcb_prod_skz_final_v

scraper.v_profibagr_input
scraper.v_profibagr_search_queue
```

These must not automatically become part of the production architecture simply because they already exist.

---

# 39. Legacy migration map

Initial target classification:

| Current object                     | Current purpose                     | Target                                                            |
| ---------------------------------- | ----------------------------------- | ----------------------------------------------------------------- |
| `public.skz`                       | CSV copy of POHODA SKz              | replace with `source_pohoda.stock_current`                        |
| `public.skz_transformed_v`         | identifier transformation           | preserve logic, migrate toward `core.product_search_identifier_v` |
| `public.jcb_prod`                  | previous Profibagr experiment       | inspect, then move to `legacy` or delete                          |
| `public.jcb_prod_skz_final_v`      | previous analytical comparison      | move to `legacy`; future replacement belongs in analytical DB     |
| `scraper.v_profibagr_input`        | Profibagr input abstraction         | retain concept; refactor against new core/source model            |
| `scraper.v_profibagr_search_queue` | deduplicated Profibagr search queue | retain concept; refactor against new core/source model            |

Before moving or deleting any object, inspect PostgreSQL dependencies.

---

# 40. Migration strategy

Migration should be incremental.

## Step 1 — inventory

Inventory all existing:

```text id="rnjkwc"
tables
views
materialized views
sequences
functions
schemas
roles
dependencies
```

Classify every existing object:

```text id="w6o2n1"
KEEP
MIGRATE
REPLACE
LEGACY
DELETE
```

---

## Step 2 — create target schemas

Create:

```text id="ubek2o"
source_pohoda
core
etl
scraper
export
legacy
```

Do not move legacy objects yet.

---

## Step 3 — implement POHODA read-only ETL

Connect directly from Linux to the production MSSQL database.

Implement full daily synchronization.

Populate:

```text id="sy7jfg"
source_pohoda.stock_current
etl.pohoda_sync_run
core.product
core.own_price_history
```

---

## Step 4 — validate against current CSV import

Compare:

```text id="fxge23"
source_pohoda.stock_current
```

against:

```text id="awme8r"
public.skz
```

for expected fields and counts.

Only after successful validation should the CSV-based source be considered obsolete.

---

## Step 5 — migrate scraper input

Replace dependency:

```text id="h5p0l0"
public.skz / public.skz_transformed_v
```

with the new operational data contract.

Preserve existing suffix transformation behavior until a tested replacement exists.

---

## Step 6 — migrate Profibagr history

Once the target scraper tables are ready, change the Profibagr scraper from:

```text id="g3dz0s"
CSV only
```

to:

```text id="le255s"
RAW CSV
+
PostgreSQL operational history
```

---

## Step 7 — isolate legacy

After dependencies have been removed, move obsolete experimental objects into:

```text id="4u5nsj"
legacy
```

or delete them after explicit review.

---

# 41. Public schema policy

New project objects must not be created in:

```text id="vp495j"
public
```

The long-term goal is for `public` to contain no Price Monitor application model.

Explicit schemas make object ownership and responsibilities clear.

---

# 42. Current open database decisions

The following issues are intentionally not finalized yet.

## POHODA accounting-year database behavior

It still needs to be confirmed whether a new POHODA accounting database is created during year transition and whether:

```text id="5df1ce"
SKz.ID
```

remains stable across that transition.

The current architecture is safe because:

```text id="yd0wy9"
core.product.product_id
```

is independent from both `IDS` and the raw POHODA technical ID.

---

## Historical and alternative P/N management

The final implementation of:

```text id="s9eky9"
core.product_identifier
```

and its management UI is backlog.

The database model must remain compatible with adding this functionality later.

---

## Analytical database

The detailed schema of:

```text id="2zokbx"
sandix_price_analytics
```

will be designed after multiple competitor datasets exist.

This is intentional.

The analytical model should follow actual comparison requirements rather than assumptions made during the first scraper implementation.

---

# 43. Target operational data flow

The target end-to-end operational flow is:

```text id="vz8vby"
POHODA / MSSQL
      │
      │ SELECT ONLY
      ▼
POHODA ETL
      │
      ├─────────────► etl.pohoda_sync_run
      │
      ▼
source_pohoda.stock_current
      │
      ├─────────────► core.product
      │
      ├─────────────► core.own_price_history
      │
      ▼
core.product_current_v
      │
      ▼
product search identifiers
      │
      ▼
scraper search queue
      │
      ▼
competitor scraper
      │
      ├─────────────► RAW CSV
      │
      ▼
scraper.scrape_run
      │
      ▼
scraper.search_request
      │
      ├─────────────► scraper.search_request_product
      │
      ▼
scraper.offer_observation
      │
      ▼
export.*
      │
      ▼
future analytics ETL
      │
      ▼
sandix_price_analytics
      │
      ▼
Metabase
```

---

# 44. Core invariants

The following database rules should be treated as architectural invariants.

1. PostgreSQL uses its own stable `product_id`.
2. `IDS` is data, not a primary key.
3. Source POHODA IDs are preserved for traceability.
4. Own Sandix price changes are historized and identical snapshots are not stored repeatedly.
5. Competitor observations are append-only, and every offer is retained.
6. Zero-result searches are stored separately from scraper failures.
7. One HTTP search may map to multiple Sandix products and should be deduplicated before execution.
8. Monetary values use decimal types and currency is stored explicitly in the observed currency.
9. Historical competitor data has no automatic retention limit.
10. RAW CSV remains an audit layer.
11. New project objects do not belong in `public`.
12. Legacy objects are migrated deliberately, not reused accidentally.
13. Existing identifier transformation logic must be preserved until its replacement has been tested.
