## Implementation Tasks

- [x] Add OpenSpec delta specs for active Tushare API cache behavior.
- [x] Add tests for cache key canonicalization and policy decisions.
- [x] Add Django model and migration for MySQL-backed external API cache rows.
- [x] Implement cache store helpers with hit, miss, expired, write, and failure behavior.
- [x] Integrate cache controls and cache lookup/write into `TushareApiClient.query()` closest to `pro.query(...)`.
- [x] Add tests for `TushareApiClient` hit, miss, expired, bypass, and uncached policy paths.
- [x] Thread job-level cache controls into Tushare collection execution where job config is available.
- [x] Update collector external API spec/docs to mark Tushare API cache as active behavior.
- [x] Run targeted backend tests and OpenSpec validation.
