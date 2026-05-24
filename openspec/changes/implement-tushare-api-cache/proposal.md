## Why

Long-running collector jobs repeatedly call the same upstream Tushare APIs during retries, reruns, and development validation. A cache at the Tushare API boundary reduces repeated external requests, rate-limit waiting, and exposure to upstream instability without changing business table semantics.

## What Changes

- Add a MySQL-backed raw response cache for Tushare API calls at the closest collector-owned boundary to `pro.query(...)`.
- Store canonical raw API responses keyed by provider, API name, semantic parameters, and raw response schema version.
- Exclude caller-selected `fields` from the cache key when the cache entry stores a complete canonical raw response.
- Add per-job/per-call cache controls so jobs can enable, bypass, or override cache behavior without relying on a global environment switch.
- Keep TTL as a system cache policy by API/data category, with optional task-level override for exceptional runs.
- Add cache observability for hit, miss, expired, disabled, and bypassed calls.
- Do not implement DB preflight skip in this change; financial statement schedules keep their current business semantics.

## Capabilities

### New Capabilities

- `tushare-api-cache`: MySQL-backed raw response caching for Tushare API calls, including cache policy, cache controls, and observability.

### Modified Capabilities

- `collector-external-api`: Promote external API response caching from deferred enhancement to an active Tushare cache requirement.

## Impact

- Backend Django model and migration for cached Tushare API responses.
- `backend/saa_collector/third_party/tushare_api_client.py` cache lookup/write integration.
- Tushare service call sites may pass cache controls derived from job configuration where needed.
- Backend tests for cache key canonicalization, cache hit/miss/expiry, bypass behavior, and field handling.
- Deployment note: production MySQL stores cache rows; no `saa-conf` volume is required for this first version.
