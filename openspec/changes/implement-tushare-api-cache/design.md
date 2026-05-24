## Overview

Implement Tushare API response caching at the `TushareApiClient.query()` boundary, immediately around the real `pro.query(...)` call. This keeps caching below collector business services and above the upstream SDK, so balance sheet, income statement, cash flow, dividend, stock basic, and other Tushare query users share one policy.

The first version uses MySQL through Django ORM because production has enough space and shared database storage avoids per-container cache fragmentation. The cache stores raw response records that can be converted back into a DataFrame-compatible result before returning to existing service code.

## Decisions

- Scope: Tushare only.
- Storage: MySQL model in collector backend.
- Default control: cache is enabled by job/call configuration, not by a global environment switch.
- TTL policy: configured by code-level API category defaults, with optional task-level override.
- Financial statement semantics: API cache only; no DB preflight skip in this change.
- Realtime APIs: default policy does not cache high-volatility APIs such as `daily` unless explicitly overridden.

## TTL Policy

Industry guidance is consistent on two points: TTL should match the underlying data change rate and stale-data risk, and different resource types can use different TTLs instead of one universal value. For collector, that means TTL belongs in a system cache policy keyed by API/data category.

Task configuration should expose operational controls:

- `api_cache_enabled`: allow cache for this job.
- `api_cache_bypass`: force upstream calls for this job.
- `api_cache_ttl_seconds`: optional override for exceptional jobs.

It should not require normal schedules to choose per-API TTLs. Defaults remain in code/configuration close to the Tushare API policy so they can be reviewed with data semantics.

Initial default policy:

- financial statement APIs and dividend/capital history: 30 days.
- `stock_basic`: 7 days.
- quote/realtime-like APIs such as `daily`: not cached by default.
- unknown APIs: not cached by default.

## Cache Key And Value

The canonical key input includes:

- provider: `tushare`
- API name: the `sub_resource` passed to `query`
- semantic params: normalized keyword args that affect upstream response
- raw response schema version: `tushare-raw-v1`

Caller-selected `fields` are excluded from the cache key because the stored value is intended to be the canonical raw response. On a cache hit, the client applies caller field selection to the cached DataFrame before returning. If an API cannot safely return complete records without a `fields` argument, that API should be disabled for cache until a canonical field set is explicitly defined.

The cache record stores:

- provider
- api_name
- cache_key
- canonical_call_json
- params_json
- fields
- response_json
- raw_response_schema_version
- expires_at
- hit_count
- last_hit_at
- created_at / updated_at

## Runtime Flow

1. `TushareApiClient.query(sub_resource, fields='', **kwargs)` receives optional cache controls.
2. If cache is disabled or bypassed, call upstream through the current rate-limited/retried path.
3. If the API policy has no TTL, log `cache disabled by policy` and call upstream.
4. Build canonical key excluding `fields`.
5. Look up non-expired cache entry.
6. On hit, increment hit metadata, log hit, return cached records as a DataFrame with caller field filtering.
7. On miss or expired entry, call upstream through current limiter/retry logic, store raw records with expiry, then return the upstream result.

Cache misses still use the existing rate limiter and retry behavior. Cache hits skip the external API call and therefore skip rate-limit wait for that call.

## Failure Behavior

The cache must not make collection more fragile. If cache read/write fails, the client logs a warning and proceeds as a cache miss through the normal upstream path. Upstream API errors keep current retry and exception behavior.

## Tests

Add focused tests for:

- canonical cache keys ignore `fields` and normalize params.
- cache hit returns a DataFrame and does not call `pro.query`.
- expired cache calls upstream and refreshes the entry.
- bypass/disabled controls call upstream.
- uncached API policy calls upstream.
- cache storage failures degrade to upstream calls.
