# Collector Data Configuration Specification

## Purpose

Define the collector data type configuration model and how backend and frontend code consume it.

Related docs:
- `../../../docs/plans/2026-04-03-data-type-configuration-refactoring.md`
- `../../../docs/plans/2026-03-24-completeness-calculator-design.md`

## Requirements

### Requirement: Data type metadata must have a backend single source of truth

Collector data type metadata SHALL be defined in backend configuration and exposed to the frontend through an API.

#### Scenario: Adding a data type
- **WHEN** a new data type is added
- **THEN** its key, label, table, group, ordering, date requirements, stock-level behavior, stock column, and completeness support SHALL be defined in backend configuration
- **AND** frontend pages SHALL discover the data type through the data-types API rather than a duplicated hardcoded list

#### Scenario: Frontend starts
- **WHEN** the collector frontend initializes
- **THEN** it SHALL load data type configuration once
- **AND** shared components SHALL use the loaded configuration for labels, groups, filters, and supported workflows

### Requirement: Completeness logic must respect data type metadata

Completeness calculations SHALL use a data type's configured completeness model, data frequency, stock-level behavior, date requirements, security scope, and stock column metadata from the data type configuration.

Completeness models SHALL describe what a heatmap cell means independently from collection frequency:

| Model | Intended data shape | Heatmap denominator |
| --- | --- | --- |
| `calendar` | Trading calendar data such as `trade_days` | Expected calendar/trading-day periods in the selected range |
| `snapshot_security` | Security master data such as `stock_info` | Securities active in the cell period, bounded by listing and delisting dates when available |
| `periodic_security` | Security-period records such as quotes, financial statements, capital, and index weights | Active securities expected for the configured report or quote period |
| `event_security` | Irregular security events such as dividends | Event presence in the cell period; absence of an event SHALL NOT be treated as missing security-period data |
| `non_stock_periodic` | Date-based non-security records such as index, board, industry, or valuation series | Configured non-security objects or, when no object universe is configured, period presence |

#### Scenario: Calculating stock-level completeness
- **WHEN** a data type is stock-level and date-based
- **THEN** completeness SHALL compare expected symbol/period combinations with existing records according to its completeness model

#### Scenario: Calculating non-stock completeness
- **WHEN** a data type is not stock-level
- **THEN** completeness SHALL use the configured table and date semantics without requiring stock codes

#### Scenario: Calculating event completeness
- **WHEN** a data type uses the `event_security` completeness model
- **THEN** a heatmap cell SHALL be complete when at least one event exists in the cell period
- **AND** a period with no events SHALL be returned as not applicable rather than as a zero completeness value
- **AND** the calculation SHALL NOT divide event records by all active securities because most active securities are not expected to have an event every period

#### Scenario: Calculating security master snapshot completeness
- **WHEN** a data type uses the `snapshot_security` completeness model
- **THEN** the denominator SHALL be securities active during the period
- **AND** active security boundaries SHALL use listing and delisting dates when available
- **AND** missing or unavailable delisting dates MAY be treated as open-ended until the security master provides real delisting boundaries

#### Scenario: Data type does not support integrity check
- **WHEN** a data type is marked as not supporting integrity checks
- **THEN** it SHALL be hidden from integrity report filters and repair-plan generation

### Requirement: Data browsing must be configuration-driven

Data browse views SHALL use data type configuration for table selection, display labels, date handling, stock column behavior, and grouping.

#### Scenario: Browsing by type
- **WHEN** a user selects a data type in the type browse view
- **THEN** the frontend SHALL render the configured label and request the configured data type key
- **AND** the backend SHALL query the table and columns associated with that key

#### Scenario: Browsing by stock
- **WHEN** a user browses a stock-level data type by stock
- **THEN** the backend SHALL use the configured stock column to filter records
