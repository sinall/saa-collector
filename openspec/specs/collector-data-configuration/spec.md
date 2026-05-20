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

Completeness calculations SHALL use data frequency, stock-level behavior, date requirements, and stock column metadata from the data type configuration.

#### Scenario: Calculating stock-level completeness
- **WHEN** a data type is stock-level and date-based
- **THEN** completeness SHALL compare expected symbol/period combinations with existing records

#### Scenario: Calculating non-stock completeness
- **WHEN** a data type is not stock-level
- **THEN** completeness SHALL use the configured table and date semantics without requiring stock codes

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
