# PROJECT_CONTEXT

## Purpose

Sandix Price Monitor tracks competitor prices for JCB spare parts to support future price adjustments.

## Scope

- Phase 1 focuses on competitor selling prices.
- Supplier purchase-price comparison is a later, separate phase.
- The system should stay extensible to more competitors and later suppliers.

## Architecture

```text
Sandix / POHODA data
        |
        v
PostgreSQL source data
        |
        v
Transformation and scraper-input views
        |
        v
Python scrapers
        |
        +------> RAW CSV archive
        |
        v
PostgreSQL price history
        |
        v
SQL analytical layer
        |
        v
Metabase
```

## Stable design decisions

- PostgreSQL is the system of record.
- CSV is a RAW audit/debug layer, not the primary database.
- Scrapers collect facts and must not contain pricing business logic.
- Prefer HTTP scraping over browser automation.
- Each competitor gets its own scraper or adapter.
- Scrapers should consume stable PostgreSQL views rather than internal tables where possible.
- Preserve both original and transformed part numbers for traceability.
- Historical and alternative part numbers are first-class data.
- Multiple competitor results must be preserved as raw candidates; the first result is not automatically correct.
- Technical failures must be distinct from valid `NOT_FOUND` results.
- Duplicate searches should be removed before HTTP requests where practical.

## Matching principles

- Strict normalization: trim and uppercase.
- Loose normalization may additionally remove separators such as `/`, `-`, and spaces.
- Loose matching is only a helper; it must not by itself establish a definitive commercial match when ambiguity exists.

## Security and access

- Scraper database access is read-only.
- The dedicated PostgreSQL role is `price_scraper_ro`.
- Credentials must stay out of Git and be supplied through environment variables or `.env`.
