## Overview

Move default API cache enablement into collect job configuration construction. This keeps cache controls task-local, as decided for the cache feature, while avoiding per-schedule manual setup.

## Decisions

- Default `api_cache_enabled` to `True` for newly created collection jobs.
- Top-level job config values take precedence over nested `params` values.
- Nested `params` values are still recognized for schedules, because schedule params are already the operator-facing configuration bag.
- `api_cache_bypass` and `api_cache_ttl_seconds` are included only when explicitly provided.
- APIs without TTL policy still log disabled-by-policy and call upstream.

## Tests

- Shared config builder defaults cache on.
- Schedule-created jobs include cache controls.
- Executor reads cache controls from nested params when top-level values are absent.
