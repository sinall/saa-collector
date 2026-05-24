## MODIFIED Requirements

### Requirement: External API response caching is implemented for Tushare

External API response caching SHALL be active for Tushare `query` calls when enabled by job or call configuration, while remaining unimplemented for other providers until dedicated changes add them.

#### Scenario: Tushare cache is implemented
- **WHEN** Tushare response caching is enabled for a cacheable API call
- **THEN** it SHALL be integrated at the `TushareApiClient.query()` layer closest to `pro.query(...)`
- **AND** cache keys SHALL include provider, API name, canonical semantic parameters, and raw response schema version
- **AND** cache keys SHALL NOT include caller-selected `fields` when the cache value stores complete raw responses
- **AND** cached values SHALL store external API raw responses rather than transformed business-table records
- **AND** logs SHALL distinguish cache hit, miss, expired, disabled, and bypassed entries

#### Scenario: Cache is not enabled for the job or call
- **WHEN** cache is disabled or bypassed by job or call configuration
- **THEN** Tushare API calls SHALL use the current direct request path

#### Scenario: Non-Tushare provider is used
- **WHEN** collector calls an external provider other than Tushare
- **THEN** this change SHALL NOT require response caching for that provider
