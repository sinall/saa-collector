## Overview

Promote financial statement date semantics from a generic `date` column to explicit domain fields. Collector raw financial statement tables will store the accounting period as `report_date` and the public report date as `disclosure_date`. This keeps foundational data aligned with finance terminology while allowing mfactor and other consumers to apply point-in-time rules without depending on provider-specific field names.

## Schema

The following collector-owned tables are in scope:

- `saa_raw_balance_sheet`
- `saa_raw_income_statement`
- `saa_raw_cash_flow_statement`
- `saa_raw_main_business`

Target shape:

```sql
symbol DATE-KEY OWNER COLUMN:
  symbol
  report_date
  disclosure_date
```

`report_date` replaces the current `date` column and remains part of the primary key. `disclosure_date` is nullable because older or non-Tushare sources may not provide actual disclosure dates immediately.

Recommended indexes:

- primary key: `(symbol, report_date)`
- lookup index: `(disclosure_date)`
- point-in-time lookup index where useful: `(symbol, disclosure_date, report_date)`

## Field Semantics

- `report_date`: financial reporting period end date, mapped from provider fields such as Tushare `end_date`.
- `disclosure_date`: date the financial report was disclosed to the market, mapped from Tushare `f_ann_date` first and `ann_date` as fallback.
- `date`: not a financial statement domain field. It may appear only as a transitional alias in views that intentionally preserve legacy consumers.

## Migration

The migration should be idempotent enough for operator reruns:

1. Rename raw statement `date` columns to `report_date` when needed.
2. Add `disclosure_date` when missing.
3. Rebuild primary keys from `(symbol, date)` to `(symbol, report_date)`.
4. Backfill `disclosure_date` for existing rows using theoretical report availability dates:
   - Annual report: `report_date + 120 days`
   - Q1, half-year, and Q3 reports: `report_date + 60 days`
   - Fallback for unexpected period ends: `report_date + 90 days`
5. Leave actual disclosure-date correction to future collection refresh jobs or operator SQL using provider data.

## Collection Mapping

Tushare statement collection should request provider disclosure fields for report-like APIs and transform them into collector fields:

```text
end_date                 -> report_date
COALESCE(f_ann_date, ann_date) -> disclosure_date
```

Provider field names should not leak into downstream table contracts. If source audit fields are later needed, they can be added separately as source-prefixed fields.

## Derived Views

Collector-owned derived SQL should expose `report_date` and `disclosure_date`. Transitional compatibility may include `report_date AS date`, but new collector code should use `report_date` directly.

For combined statements, a row's `disclosure_date` should be the latest non-null disclosure date among joined component statements, because the combined row is only fully available after all included components are available.

## Consumer Impact

This change intentionally updates collector-owned migrations and code. Other repositories may consume statement tables or views through manually managed SQL. Those consumers should update their views and queries to prefer `report_date` and `disclosure_date`; compatibility aliases can be kept temporarily where needed.

## Tests

- Migration SQL contains report-date rename, disclosure-date add, backfill, and primary-key rebuild steps for all four tables.
- Tushare statement transformation maps `end_date`, `f_ann_date`, and `ann_date` into `report_date` and `disclosure_date`.
- Statement saving and maintenance use `(symbol, report_date)`.
- Collector data browsing and completeness paths use `report_date` for the affected data types.
