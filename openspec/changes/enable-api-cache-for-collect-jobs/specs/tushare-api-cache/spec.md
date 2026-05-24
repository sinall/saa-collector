## MODIFIED Requirements

### Requirement: Collection jobs enable Tushare API cache by default

Collector SHALL enable Tushare API cache for newly created collection jobs unless the job configuration explicitly disables or bypasses it.

#### Scenario: Schedule creates a collect job
- **WHEN** a collect schedule creates a collect job
- **THEN** the job config SHALL include `api_cache_enabled: true` by default
- **AND** schedule params MAY override `api_cache_enabled`, `api_cache_bypass`, or `api_cache_ttl_seconds`

#### Scenario: Job params contain cache controls
- **WHEN** a job config does not define cache controls at the top level
- **AND** its nested `params` define cache controls
- **THEN** the executor SHALL apply the nested cache controls to Tushare API calls

#### Scenario: API has no cache policy
- **WHEN** API cache is enabled for a job
- **AND** the Tushare API name has no positive TTL policy
- **THEN** collector SHALL call upstream without caching that API
