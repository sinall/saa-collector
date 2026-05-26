## Why

Collector schedules currently treat date parameters as plain strings and only reliably support absolute dates or ad hoc values such as `today`. Operators want to configure rolling collection windows with familiar finance notation, where `T-1` usually means one trading day earlier rather than one calendar day earlier.

## What Changes

- Add relative date expressions for collect schedule date parameters.
- Define `T±N` and `T±Ntd` as trading-day offsets, with `td` optional.
- Define `T±Nd` as calendar-day offsets.
- Keep `T`, `today`, and `YYYY-MM-DD` inputs valid.
- Standardize schedule date parameters on `start_date` / `end_date` through validation, persistence, and execution, while still accepting legacy aliases for backward compatibility.
- Resolve trading-day offsets against collector's trading calendar rather than weekday-only heuristics.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `collector-schedules`: Schedule date parameters accept relative date expressions with explicit trading-day and calendar-day semantics.

## Impact

- Backend schedule serializers, validation, and job parameter normalization.
- Collect execution paths that read `start_date` / `end_date`.
- Trading calendar lookup logic for trading-day offsets.
- Frontend schedule form hints and related tests/documentation.
