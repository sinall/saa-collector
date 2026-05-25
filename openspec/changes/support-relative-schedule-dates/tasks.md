## 1. Backend date parsing and validation

- [x] 1.1 Add failing backend tests for schedule date expressions covering `T`, `T-180`, `T-1td`, `T-30d`, invalid syntax, and non-trading-day resolution.
- [x] 1.2 Implement a shared schedule date-expression parser that distinguishes trading-day offsets from calendar-day offsets and resolves trading days from `saa_trade_days`.
- [x] 1.3 Update collect schedule serializers or validation helpers to accept relative expressions while preserving raw operator-entered values.

## 2. Execution-path compatibility

- [x] 2.1 Add failing tests showing schedule execution uses identical values for `date_start` / `date_end` and `start_date` / `end_date`.
- [x] 2.2 Normalize schedule date parameter aliases before plan creation and collect execution so manual and automatic triggers resolve the same effective dates.
- [x] 2.3 Update collect execution paths to resolve relative expressions immediately before collector service calls.

## 3. Frontend and operator guidance

- [x] 3.1 Update the collect schedule form hints or help text to document `T±N` as trading-day offsets and `T±Nd` as calendar-day offsets.
- [x] 3.2 Add or update frontend tests for the revised operator-facing examples if coverage exists for the schedule form.

## 4. Verification

- [x] 4.1 Run targeted backend tests for schedule validation and execution.
- [x] 4.2 Run relevant frontend validation or test commands for the schedule UI changes.
