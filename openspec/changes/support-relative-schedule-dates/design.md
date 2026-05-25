## Context

Collector schedules persist operator-entered parameters in `CollectSchedule.params` and later pass them into collect plan execution. Current date handling is fragmented: some paths accept raw strings such as `today`, execution code reads both `date_start`/`date_end` and `start_date`/`end_date` inconsistently, and there is no shared parser for trading-day offsets. Because trading-day offsets depend on the collector trading calendar, the parser must live on the backend near schedule validation and execution rather than in the frontend alone.

## Goals / Non-Goals

**Goals:**

- Let schedule operators express rolling windows with `T`, `T±N`, `T±Ntd`, and `T±Nd`.
- Treat bare `T±N` as trading-day offsets to match common finance notation.
- Resolve trading-day offsets against persisted trade days rather than weekday-only math.
- Keep existing absolute dates and `today` inputs working.
- Normalize date parameter aliases so schedule creation, update, manual trigger, and auto execution all see the same effective values.

**Non-Goals:**

- Add similar relative-date syntax to integrity reports or unrelated collector APIs in this change.
- Introduce market-specific calendars beyond the existing collector trade-day table.
- Change schedule storage to a typed date model; raw operator expressions remain persisted strings.

## Decisions

- Add a shared backend parser for schedule date expressions.
  Rationale: validation and execution need identical semantics, and tests can lock behavior in one place.
  Alternative considered: parse only in execution code. Rejected because invalid expressions would be accepted at save time and fail later during execution.

- Use the existing `saa_trade_days` table as the source of truth for trading-day offsets.
  Rationale: collector already owns that calendar and uses it in completeness and market-date logic.
  Alternative considered: derive trading days from weekday rules. Rejected because holidays and exchange closures would be wrong.

- Interpret `T±N` and `T±Ntd` identically as trading-day offsets, while `T±Nd` remains calendar-day offsets.
  Rationale: this matches the operator expectation discussed for fund settlement and other finance workflows.
  Alternative considered: make no-suffix mean calendar day. Rejected because it conflicts with current domain language.

- Preserve operator-entered expressions in schedule params and resolve them at execution time.
  Rationale: relative dates should move as the schedule runs; persisting resolved absolute dates would freeze the window.
  Alternative considered: resolve to absolute dates during schedule save. Rejected because recurring schedules would stop being relative.

- Normalize `date_start`/`date_end` and `start_date`/`end_date` into one canonical view before validation and execution.
  Rationale: current alias drift is an existing bug risk and would make relative-date support unreliable.

## Risks / Trade-offs

- [Trading calendar missing or stale] → Mitigation: fail validation or execution with an explicit error that trading-day resolution requires available `saa_trade_days` data.
- [Different entry points diverge on parser usage] → Mitigation: route serializer validation and execution through the same shared helper and cover both with tests.
- [Operators assume `T` itself means latest trading day] → Mitigation: document the exact semantics in the schedule UI and spec; reserve trading-day behavior for offset expressions.
- [Legacy schedules stored with only one alias key] → Mitigation: normalize both aliases on read/write without requiring a data migration.
