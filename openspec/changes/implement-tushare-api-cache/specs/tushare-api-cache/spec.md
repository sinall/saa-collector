## ADDED Requirements

### Requirement: Tushare API calls can use a MySQL-backed raw response cache

Collector SHALL support caching Tushare `query` raw responses in MySQL when a job or call enables API caching.

#### Scenario: Cache is enabled for a cacheable Tushare API
- **WHEN** a Tushare `query` call is made with API cache enabled
- **AND** the API policy defines a positive TTL
- **THEN** collector SHALL look up a MySQL cache row before calling upstream Tushare
- **AND** the cache row SHALL store raw response records, not transformed business-table records

#### Scenario: Cache is disabled or bypassed for a job
- **WHEN** a job or call disables or bypasses API cache
- **THEN** collector SHALL call upstream Tushare through the normal rate-limited request path
- **AND** it SHALL NOT read or write cache rows for that call

### Requirement: Tushare cache keys are canonical and field-independent

Tushare cache keys SHALL identify semantic upstream calls without depending on caller-selected output fields.

#### Scenario: Same semantic call requests different fields
- **WHEN** two Tushare calls use the same API name and semantic parameters
- **AND** they request different `fields`
- **THEN** collector SHALL derive the same cache key
- **AND** cached values SHALL remain reusable for callers that need different fields when the stored raw response contains those fields

#### Scenario: Parameters are supplied in different order
- **WHEN** two Tushare calls use equivalent keyword parameters in different order
- **THEN** collector SHALL derive the same cache key

### Requirement: Tushare cache TTL is governed by API policy with task override

Collector SHALL choose default cache TTLs from system policy by Tushare API/data category and allow exceptional job-level overrides.

#### Scenario: High-volatility API has no default cache policy
- **WHEN** a Tushare API such as daily quote data has no positive default TTL
- **AND** no job override is provided
- **THEN** collector SHALL call upstream Tushare without caching

#### Scenario: Job supplies a TTL override
- **WHEN** a job enables API cache and supplies `api_cache_ttl_seconds`
- **THEN** collector SHALL use that TTL for cache expiry for eligible calls in that job

### Requirement: Tushare cache is observable and non-critical

Collector SHALL log cache outcomes and SHALL degrade to upstream calls if cache storage fails.

#### Scenario: Cache entry is hit
- **WHEN** a valid cache row is found
- **THEN** collector SHALL return the cached raw response converted to the existing query result shape
- **AND** it SHALL log a cache hit with provider, API name, and cache key context

#### Scenario: Cache entry is expired
- **WHEN** a matching cache row exists but has expired
- **THEN** collector SHALL treat the call as a cache miss
- **AND** it SHALL call upstream Tushare and refresh the cache row

#### Scenario: Cache storage fails
- **WHEN** cache read or write raises an unexpected error
- **THEN** collector SHALL log the cache failure
- **AND** it SHALL continue through the normal upstream Tushare request path
