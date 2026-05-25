## ADDED Requirements

### Requirement: Schedule date parameters support relative date expressions

Collector schedules SHALL accept relative date expressions for start and end date parameters and preserve them for recurring execution.

#### Scenario: User saves a schedule with trading-day offsets

- **WHEN** a user creates or updates a collect schedule with `date_start`, `date_end`, `start_date`, or `end_date` values such as `T-180`, `T+2`, or `T-1td`
- **THEN** the backend SHALL accept those expressions as valid schedule date inputs
- **AND** it SHALL persist the operator-entered relative expressions instead of resolving them to fixed absolute dates

#### Scenario: User saves a schedule with calendar-day offsets

- **WHEN** a user creates or updates a collect schedule with values such as `T-30d` or `T+7d`
- **THEN** the backend SHALL accept those expressions as valid schedule date inputs
- **AND** it SHALL interpret the `d` suffix as calendar-day arithmetic

#### Scenario: User saves a schedule with an invalid relative expression

- **WHEN** a user creates or updates a collect schedule with an unsupported date expression
- **THEN** the backend SHALL reject the request with a validation error

### Requirement: Schedule execution resolves date expressions consistently

Collector schedule execution SHALL resolve stored date expressions with consistent alias and calendar semantics before calling collectors.

#### Scenario: Bare T offsets use trading-day semantics

- **WHEN** a schedule executes with `T±N` or `T±Ntd` in its stored date parameters
- **THEN** the collector SHALL resolve those expressions as trading-day offsets
- **AND** bare `T±N` SHALL behave the same as `T±Ntd`

#### Scenario: Trading-day offsets use the collector trading calendar

- **WHEN** a schedule executes with a trading-day offset and the current date falls on a weekend or market holiday
- **THEN** the collector SHALL resolve the offset using persisted trade days from the collector trading calendar
- **AND** it SHALL NOT approximate trading days with weekday-only subtraction

#### Scenario: Date aliases resolve to the same effective values

- **WHEN** a schedule is stored with `date_start` / `date_end`, `start_date` / `end_date`, or a mix of both
- **THEN** schedule validation and execution SHALL use the same effective start and end dates
- **AND** manual and automatic schedule triggers SHALL observe identical resolved values
