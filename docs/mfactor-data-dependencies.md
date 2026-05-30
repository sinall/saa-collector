# mfactor Data Dependencies

This document records how `mfactor` depends on market, fundamental, and reference data, and how `saa-collector` should evolve to provide that data.

`mfactor` is one of the primary consumers of `saa-collector`. The intended direction is:

- `saa-collector` provides all external/raw/normalized data needed by `mfactor`.
- `mfactor` owns only its internal calculations and analysis outputs, such as factor values, factor weights, IC/performance results, and analyzer runs.
- Duplicated external data loading paths should be phased out or reduced to compatibility bridges.

## Boundary

### Data Collector Should Own

`saa-collector` should own data that originates from external market or fundamental data providers, or data that can be deterministically normalized from those provider records:

- Trading calendars
- Stock/security master data
- Daily and latest prices
- Monthly and quarterly price aggregates derived from daily prices
- Financial statements and combined financial statement views
- Dividends
- Capital changes
- Index constituents and weights
- Industry dictionaries and industry constituents
- Board/industry valuation data
- Stock status metadata needed for analysis, such as ST flags and suspended/paused status
- Index quotes

Collector-owned views or derived tables should be reusable source data assets, not `mfactor`-specific adapter contracts. For example, monthly prices, quarterly prices, and combined financial statements are common derived data and belong on the collector side.

If `mfactor` needs field names, symbol formats, or return shapes that are specific to its analyzer APIs, those adapter objects should be owned by `mfactor` and built on top of collector-owned source data.

Before adding new collector-owned data objects, map each current `mfactor` source table to existing `saa` objects. Many source tables already have adequate or near-adequate replacements in the collector schema. New collector jobs or tables should be added only when no adequate existing `saa` source exists, or when the existing source lacks required fields, freshness, or data quality.

Current database inspection indicates that several `mfactor` source tables have already been migrated to `saa` with an `saa_` prefix. The immediate collector-side gap is mostly collection and refresh governance, not table creation.

### mfactor Should Own

`mfactor` should own data that is produced by factor research and analysis workflows:

- Factor definitions and metadata
- Generated factor values
- Analyzer run records
- IC results
- Factor weights
- Performance results
- Portfolio/position outputs derived from analyzer configuration

Those data sets are not external source data. They are outputs of `mfactor` logic and should not be scheduled as collector data types.

## Current Production Database Split

Production configuration currently uses separate databases:

- `saa-collector`: `DATABASE_NAME=saa`
- `mfactor`: `DATABASE_NAME=mfactor`

This means `saa-collector` writing `saa_*` tables is not automatically enough for `mfactor` runtime tables such as `trade_days`, `securities`, `prices`, or `index_weights`.

There are two viable long-term approaches:

1. Make `mfactor` read external data from the `saa` schema directly, keeping only computed outputs in `mfactor`.
2. Keep `mfactor` runtime source tables, but add an explicit sync pipeline from collector-managed `saa` tables into `mfactor`.

The first approach is preferable because it reduces duplicated storage and duplicated freshness problems.

The preferred direct-read approach can still use `mfactor`-owned adapter views, adapter tables, or Python repository functions. In that model, collector owns reusable data objects in the `saa` schema, while `mfactor` owns thin adapter contracts that map those objects into the shape expected by existing factor/analyzer code.

Do not introduce mandatory prefixes such as `v_` or `source_` only to mark implementation details. Existing project naming does not use those conventions consistently, and adapter contracts may not be database objects at all. If database objects are used, name them according to existing `mfactor` conventions; the name should not need to change if a view later becomes a materialized table or physical table.

## mfactor Raw Data Dependencies

`mfactor/backend/mfactor/analyzer/factor_calc.py` directly queries these `saa` schema objects during factor generation:

| Data | Current object queried by mfactor | Collector status |
| --- | --- | --- |
| Combined financial statements | `saa.saa_financial_statements_combined` | Exists as a database view; needs collector-side definition/version governance and freshness checks |
| Monthly prices | `saa.saa_monthly_prices` | Exists as a database view; needs collector-side definition/version governance and freshness checks |
| Quarterly prices | `saa.saa_quarterly_prices` | Exists as a database view; needs collector-side definition/version governance and freshness checks |
| Capital changes | `saa.saa_capitals` | Collector has `capital` data type |
| Dividends | `saa.saa_dividends` | Collector has `dividend` and composite `financial_statements` data types |

Important implication: collecting raw daily prices and raw financial statements is not sufficient unless the derived objects are also maintained.

## mfactor Runtime Data Dependencies

`mfactor` analysis code uses these local `mfactor` tables through Django models:

| mfactor table | Purpose | Should collector provide source data? | Notes |
| --- | --- | --- | --- |
| `trade_days` | Analysis calendar, month boundary calculation | Yes | Collector has `saa_trade_days`, but no automatic mfactor sync/read path |
| `securities` | Security master data | Yes | Prefer `saa_securities` because its shape matches `mfactor.securities`; use `saa_stocks` as fallback/enrichment source |
| `prices` | Daily stock prices used by analyzer/cross-section logic | Yes | Collector has `saa_prices_ex`; mapping/sync or direct read needed |
| `extras` | ST/status metadata | Yes | `saa_extras` exists with `code/date/is_st`; collector data type and schedule are missing |
| `index_quotes` | Benchmark/index quote series | Yes | `saa_index_quotes` exists; collector data type and schedule are missing |
| `index_weights` | Benchmark constituents and weights | Yes | `saa_index_weights` exists and collector has config metadata, but executor/schedule are missing |
| `industries` | Industry dictionary | Yes | `saa_industries` exists and collector has config metadata, but executor/refresh governance is missing |
| `industry_stocks` | Industry constituents by date | Yes | `saa_industry_stocks` exists and collector has config metadata, but executor/schedule are missing |

## Current `saa` Counterparts

| mfactor source table | Existing `saa` counterpart | Collector status | Next action |
| --- | --- | --- | --- |
| `trade_days` | `saa_trade_days` | Data type and executor exist; production schedule needs verification | Add or verify schedule |
| `securities` | Prefer `saa_securities`; fallback `saa_stocks` | `stock_info` writes `saa_stocks` and refreshes `saa_securities` | Verify production `stock_info` schedule |
| `prices` | `saa_prices_ex` | `historical_quote` data type and schedule exist | Map directly in mfactor adapter |
| `extras` | `saa_extras` | Data type and executor implemented | Verify production schedule |
| `index_quotes` | `saa_index_quotes` | Data type and executor implemented | Verify production schedule |
| `index_weights` | `saa_index_weights` | Data type and executor implemented | Verify production schedule |
| `industries` | `saa_industries` | Data type and executor implemented with Tushare SW2021 source | Verify production schedule |
| `industry_stocks` | `saa_industry_stocks` | Data type and executor implemented with cached Tushare member API | Verify production schedule |
| Financial statement input | `saa_financial_statements_combined` | View exists; code-level governance missing | Version view definition and add freshness checks |
| Monthly price input | `saa_monthly_prices` | View exists; code-level governance missing | Version view definition and add freshness checks |
| Quarterly price input | `saa_quarterly_prices` | View exists; code-level governance missing | Version view definition and add freshness checks |
| `factors` | Factor definitions | No | Owned by mfactor |
| `security_factor_values` | Generated factor values | No | Produced by `mfactor manage.py generate` |
| `analyzer_runs` | Analysis run records | No | Produced by mfactor analyzer workflow |
| `ics` | IC results | No | Produced by mfactor analyzer workflow |
| `weights` | Factor weights | No | Produced by mfactor analyzer workflow |
| `perf` | Performance results | No | Produced by mfactor analyzer workflow |

## Current Collector Coverage

`saa-collector` currently has data type configuration for a broad set of data:

- `trade_days`
- `stock_info`
- `quote`
- `historical_quote`
- `financial_statements`
- `balance_sheet`
- `income`
- `cash_flow`
- `main_business`
- `capital`
- `dividend`
- `valuation`
- `valuation_board`
- `valuation_industry`
- `index_weights`
- `industries`
- `csrc_industry_classifications`
- `industry_stocks`

Executor support for the mfactor source-data set now includes:

- `trade_days`
- `stock_info`
- `quote`
- `historical_quote`
- `financial_statements`
- `balance_sheet`
- `income`
- `cash_flow`
- `dividend`
- `capital`
- `main_business`
- `valuation`
- `extras`
- `index_quotes`
- `index_weights`
- `industries`
- `industry_stocks`
- `csrc_industry_classifications`
- `tick`

Configured but not currently executable as real collector jobs:

- `valuation_board`
- `valuation_industry`

For valuation, the executable collector job is the composite `valuation` data type, not the individual `valuation_board` or `valuation_industry` data types.

## Missing Collector Capabilities For mfactor

### Derived Financial Statement View

`mfactor` expects `saa.saa_financial_statements_combined`.

The object currently exists as a database view. Collector should govern it as part of the data-provider contract:

- Store the view definition in version-controlled database migration or SQL.
- Document the raw tables it depends on.
- Add freshness/completeness checks after financial statement collection.
- Keep the view shape stable for consumers, or provide a migration path when fields change.

The object should be treated as part of collector-owned normalized data, because it is derived from external financial statement data.

### Monthly and Quarterly Price Aggregates

`mfactor` expects:

- `saa.saa_monthly_prices`
- `saa.saa_quarterly_prices`

The objects currently exist as database views. Collector currently collects daily historical prices and should govern these views as deterministic aggregations over collector-managed daily price data.

These should remain derived from collector-managed daily price data, not fetched independently unless the provider supplies a materially different canonical series. The view definitions and freshness checks should be versioned with collector data governance.

### Index Constituents and Weights

`mfactor` needs benchmark constituents through `index_weights`.

`saa_index_weights` exists and collector implements `index_weights` as a first-class collector data type with:

- Index code
- Date
- Constituent stock code
- Display name
- Weight

### Quantitative Industry Data

`mfactor` needs:

- Industry dictionary: `industries`
- Industry constituents by date: `industry_stocks`

Collector currently has CSRC industry classification collection, but that is not the same as the quantitative industry exposure model used by `mfactor`.

Collector implements separate collection and normalization for the SW2021 industry taxonomy required by factor neutralization and exposure construction.

`saa_industries` and `saa_industry_stocks` already exist and now have executor support. The immediate remaining work is to verify production schedules and keep the Tushare API cache policy aligned with provider update cadence.

### Stock Status Metadata

`mfactor` uses `extras` for ST filtering and uses price records for paused/suspended filtering.

Collector should provide normalized status fields required by analysis:

- `is_st`
- `paused` or equivalent suspended status
- Effective date
- Stock code

`saa_extras` already exists with `code`, `date`, and `is_st`. Collector now has an explicit `extras` data type and executor; production schedule coverage still needs verification.

### Index Quotes

`mfactor` uses index quote history for benchmark and performance workflows.

`saa_index_quotes` already exists with a shape matching `mfactor.index_quotes`. Collector now provides index quote collection and normalized storage for benchmark indexes used by `mfactor`, including at least:

- Index code
- Trade date
- Open/high/low/close
- Previous close
- Turnover volume/value where available
- Valuation fields where available and useful

## Recommended Schedule Coverage

The following collector schedules should exist once the missing data types are implemented:

| Data type | Suggested cadence | Purpose |
| --- | --- | --- |
| `trade_days` | Daily or weekly, with future window refresh | Keep trading calendar complete |
| `stock_info` | Daily or weekly | Keep listings, delistings, names, and security metadata current |
| `historical_quote` | Daily after market close | Maintain daily price base table |
| `quote` | Intraday or after market close as needed | Site latest quote data |
| `financial_statements` | Monthly and during reporting seasons | Maintain raw statements and dividends |
| `capital` | Monthly or during reporting seasons | Maintain capital change history |
| `valuation` | Daily after provider data is ready | Maintain board/industry valuation data |
| `csrc_industry_classifications` | Monthly or quarterly | Maintain CSRC classification reference data |
| `index_weights` | Monthly or at index rebalance cadence | Maintain benchmark constituent weights |
| `industries` | Low frequency, on taxonomy updates | Maintain quantitative industry dictionary |
| `industry_stocks` | Monthly or at provider update cadence | Maintain industry constituents |
| monthly/quarterly price view governance | On schema changes and deployment | Maintain `saa_monthly_prices` and `saa_quarterly_prices` definitions and freshness checks |
| combined financial statement view governance | On schema changes and deployment | Maintain `saa_financial_statements_combined` definition and freshness checks |
| index quotes | Daily after market close | Maintain `saa_index_quotes` benchmark price history |
| stock status metadata | Daily after market close | Maintain `saa_extras` ST filters |

## Proposed Evolution Path

### Phase 1: Make Existing Gaps Explicit

- Keep `index_weights`, `industries`, and `industry_stocks` executable and covered by production schedules.
- Document that `valuation_board` and `valuation_industry` are completeness/reporting data types, while `valuation` is the executable collection data type.
- Add and run `check_mfactor_readiness` plus integrity/completeness checks for derived objects that `mfactor` depends on.
- Keep collector-side views/tables focused on reusable data assets, not `mfactor` adapter shapes.
- For each `mfactor` source table, first identify whether an existing `saa` object is already an adequate replacement. Add new collector production only for true gaps.

### Phase 2: Add Derived Objects

- Add version-controlled collector-owned definitions for the existing `saa_financial_statements_combined`, `saa_monthly_prices`, and `saa_quarterly_prices` views.
- Ensure refresh ordering: raw collection first, derived refresh second.

### Phase 3: Add mfactor Reference Data

- Implement `index_weights` collection.
- Implement `industries` collection.
- Implement `industry_stocks` collection.
- Implement index quote collection.
- Implement stock status metadata collection.

### Phase 4: Remove Duplicate Source Data Ownership

- Decide whether `mfactor` reads from `saa` directly or receives a sync from `saa`.
- Prefer direct reads from collector-owned `saa` tables/views for external source data.
- Keep only computed factor/analyzer outputs in the `mfactor` database.

### Phase 5: Automate mfactor Computation Separately

After collector data is complete, schedule `mfactor` workflows separately:

- Run factor generation to populate `security_factor_values`.
- Run analyzer workflows to populate `analyzer_runs`, `ics`, `weights`, and `perf`.

These workflows should not be modeled as collector data types, because they are not external data collection.

## Open Questions

- Should `mfactor` continue to maintain duplicated local source tables, or should it read external source data directly from the `saa` schema?
- What benchmark indexes are mandatory for initial support?
- Which industry taxonomy should be canonical for factor neutralization?
- Should monthly/quarterly prices be database views, materialized tables, or scheduled derived tables?
- Should combined financial statements be a database view or a physical table refreshed after statement collection?
- What exact symbol format should be standardized between `saa-collector` and `mfactor`: raw six-digit symbol, exchange-suffixed symbol, or both?
