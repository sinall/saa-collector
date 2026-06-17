## MODIFIED Requirements

### Requirement: Data type metadata must have a backend single source of truth

Collector data type metadata SHALL be defined in backend configuration and exposed to the frontend through an API.

#### Scenario: Financial statement data type has explicit date semantics
- **WHEN** a data type represents balance sheet, income statement, cash flow statement, combined financial statements, or main business statement data
- **THEN** its configured period column SHALL be `report_date`
- **AND** collector SHALL NOT require callers to infer financial report period from a generic `date` field

#### Scenario: Financial statement data type exposes disclosure date
- **WHEN** a financial statement table stores report records
- **THEN** collector SHALL support a nullable `disclosure_date` column representing the report's market disclosure date
- **AND** downstream point-in-time consumers SHALL be able to compare `disclosure_date` with their analysis date without interpreting provider-specific field names

### Requirement: Completeness logic must respect data type metadata

Completeness calculations SHALL use a data type's configured completeness model, data frequency, stock-level behavior, date requirements, security scope, and stock column metadata from the data type configuration.

#### Scenario: Financial statement completeness uses report periods
- **WHEN** completeness is calculated for financial statement or main business data
- **THEN** expected and existing periods SHALL be matched on `report_date`
- **AND** disclosure-date availability SHALL NOT change whether a report-period row exists
