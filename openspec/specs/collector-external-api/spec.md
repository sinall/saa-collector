# Collector External API Specification

## Purpose

Define collector behavior for Tushare/Akshare calls, rate limiting, retries, observability, and future response caching.

Related docs:
- `../../../docs/plans/2026-05-19-external-api-cache-design-notes.md`
- `../../../docs/plans/2026-05-16-collection-progress-eta-design.md`

## Requirements

### Requirement: Tushare calls must use a shared rate limiter when available

Tushare API calls SHALL enforce account-level request spacing across collector processes when Redis is configured.

#### Scenario: Redis rate limiter is available
- **WHEN** a Tushare API call is about to start
- **THEN** the client SHALL acquire the global Redis limiter
- **AND** it SHALL wait until the configured interval has elapsed since the previous shared call

#### Scenario: Redis rate limiter is unavailable
- **WHEN** the Redis limiter cannot be initialized or fails
- **THEN** the client SHALL fall back to process-local rate limiting
- **AND** it SHALL log the fallback reason

### Requirement: External API latency and limiter wait must be observable

External API logs SHALL separate real API latency from intentional limiter sleep.

#### Scenario: Tushare call completes
- **WHEN** a Tushare query returns
- **THEN** logs SHALL include returned record count, `api_elapsed_seconds`, and `rate_limit_wait_seconds`

#### Scenario: Global limiter waits
- **WHEN** the global limiter sleeps or waits on its Redis lock
- **THEN** logs SHALL include `limiter=global`, wait seconds, elapsed seconds, interval seconds, and lock wait seconds

### Requirement: External API retries must be bounded

External API transient failures SHALL be retried a bounded number of times with backoff.

#### Scenario: Tushare request has a connection timeout
- **WHEN** a request raises a connection or timeout exception
- **THEN** the client SHALL retry up to the configured maximum
- **AND** it SHALL raise a collector API exception after retries are exhausted

### Requirement: External API response caching is a deferred enhancement

External API response caching SHALL remain a proposed enhancement until implemented by a dedicated change.

#### Scenario: Cache is implemented
- **WHEN** response caching is added
- **THEN** it SHALL be integrated at the external API client layer
- **AND** cache keys SHALL include provider, API name, canonical semantic parameters, and raw response schema version
- **AND** cache keys SHALL NOT include caller-selected `fields` when the cache value stores complete raw responses
- **AND** cached values SHALL store external API raw responses rather than transformed business-table records
- **AND** logs SHALL distinguish cache hit, miss, and expired entries

#### Scenario: Parser fields change after data is cached
- **WHEN** collector parsing logic is changed to consume an additional field from an already cached API response
- **THEN** collector SHALL be able to rebuild business records from the cached raw response if that raw response contains the field
- **AND** it SHALL bypass or invalidate the cache only when the cached raw response lacks required raw fields or uses an incompatible raw schema version

#### Scenario: Cache is disabled
- **WHEN** cache is disabled by configuration
- **THEN** API calls SHALL use the current direct request path

### Requirement: Financial statement schedules must prefer business-table preflight before API cache

Financial statement schedules SHALL reduce repeated full-market work by checking local business-table coverage before relying on external API response cache when the schedule is configured for missing-data backfill.

#### Scenario: Local statement data is complete enough
- **WHEN** a financial statement schedule is configured for missing-data backfill
- **AND** the local statement tables already satisfy the configured coverage rule for a symbol
- **THEN** collector SHOULD skip external API calls, transformation, and business-table writes for that symbol
- **AND** it SHALL log the skip reason

#### Scenario: Local statement data is missing or stale
- **WHEN** any required core statement table is missing the configured coverage for a symbol
- **THEN** collector SHALL collect that symbol through the normal external API path
- **AND** API response cache MAY be used inside that path if the cache feature is enabled

#### Scenario: Schedule requires forced refresh
- **WHEN** a schedule or job is configured to force refresh recent statement revisions
- **THEN** collector SHALL NOT skip solely because historical rows exist
- **AND** the refresh window SHALL be explicit, such as a configured recent-period count
