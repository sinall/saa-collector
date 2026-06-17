## Why

Financial statement tables currently use a generic `date` column for the report period and do not store the financial report disclosure date. This makes the foundation data ambiguous and prevents downstream point-in-time analysis from distinguishing report period from market availability.

## What Changes

- **BREAKING** Rename financial statement report-period columns from `date` to `report_date` in collector-owned raw statement tables.
- Add `disclosure_date` to raw financial statement tables so collected data can record when a report became public.
- Apply the same report-date rename to `saa_raw_main_business`.
- Backfill `disclosure_date` with conservative theoretical dates during migration so existing rows remain usable until source refresh jobs replace them with actual disclosure dates.
- Update collector statement collection, maintenance, browsing, integrity, and mfactor-readiness logic to use `report_date`.
- Keep compatibility aliases only where explicitly needed for transitional views; consumer repositories such as saa-web, saa-social, and saa-facade-api may need manual view updates outside this change.

## Capabilities

### New Capabilities

### Modified Capabilities

- `collector-data-configuration`: Financial statement data types use explicit report-date and disclosure-date semantics.
- `collector-external-api`: Tushare financial statement collection maps provider report and disclosure fields into collector-owned domain fields.

## Impact

- Database tables: `saa_raw_balance_sheet`, `saa_raw_income_statement`, `saa_raw_cash_flow_statement`, and `saa_raw_main_business`.
- Collector backend: statement collection services, config-driven field mapping, statement maintenance, data browsing, completeness/integrity checks, and readiness checks.
- Derived SQL: collector-owned mfactor statement view definitions must expose clear financial date fields.
- Downstream systems: existing external views and direct consumers that depend on `date` in statement views or tables must be reviewed and updated manually by their owners.
