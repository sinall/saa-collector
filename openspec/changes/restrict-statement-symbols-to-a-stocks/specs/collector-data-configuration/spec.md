## MODIFIED Requirements

### Requirement: Data type configuration is the source of truth for data semantics

Collector data type metadata SHALL be defined in backend configuration and exposed to the frontend through an API.

#### Scenario: Data type has a security scope
- **WHEN** a data type is configured with `security_scope: a_stock`
- **THEN** collector SHALL restrict explicit collection symbols for that data type to rows in `saa_stocks` with `type='STOCK'` and `market='A'`
- **AND** collector SHALL apply that filtering before symbol-level progress tracking and external API calls

#### Scenario: Quote data allows non-stock securities
- **WHEN** quote or historical quote data is collected
- **THEN** collector SHALL NOT apply the A-stock-only scope unless that data type is explicitly configured with `security_scope: a_stock`
