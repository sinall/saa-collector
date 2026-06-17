## MODIFIED Requirements

### Requirement: External API response caching is a deferred enhancement

External API response caching SHALL remain a proposed enhancement until implemented by a dedicated change.

#### Scenario: Tushare statement parser consumes disclosure fields
- **WHEN** collector parses Tushare balance sheet, income statement, cash flow statement, or main business responses
- **THEN** it SHALL map the provider report-period field to `report_date`
- **AND** it SHALL map provider disclosure fields to `disclosure_date` using the most accurate available disclosure date first
- **AND** this parser field change SHALL be compatible with the external API cache policy by requiring cache bypass or refresh only when cached raw responses do not contain the needed raw fields

### Requirement: Financial statement schedules must prefer business-table preflight before API cache

Financial statement schedules SHALL reduce repeated full-market work by checking local business-table coverage before relying on external API response cache when the schedule is configured for missing-data backfill.

#### Scenario: Local statement data is checked after report-date migration
- **WHEN** a financial statement schedule checks whether local data is complete enough
- **THEN** it SHALL use `report_date` as the report-period key
- **AND** it SHALL not rely on the legacy `date` column for collector-owned raw statement tables
