## Why

Tushare API cache is implemented but existing schedule-created jobs do not set `api_cache_enabled` at the top level, so cache remains disabled even for cacheable APIs. Collection jobs should enable API cache by default while still allowing explicit bypass or TTL overrides.

## What Changes

- Add a shared collect job config builder that enables API cache by default.
- Use the builder for schedule-created jobs, instant collect jobs, and legacy direct job creation.
- Allow schedule/job params to override cache enablement, bypass, or TTL.
- Keep uncacheable API policy behavior unchanged; enabling cache does not cache APIs without TTL policy.

## Capabilities

### New Capabilities

### Modified Capabilities

- `tushare-api-cache`: Collection jobs enable API cache by default unless explicitly disabled or bypassed.

## Impact

- Collect job creation paths.
- Collect executor cache-control extraction.
- Tests for default cache config and params compatibility.
