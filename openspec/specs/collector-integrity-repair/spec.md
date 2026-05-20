# Collector Integrity And Repair Specification

## Purpose

Define the data integrity report, missing-item selection, repair-plan generation, and repair feedback behavior.

Related docs:
- `../../../docs/plans/2026-03-14-integrity-check-and-collect-plan-design.md`
- `../../../docs/plans/2026-03-14-integrity-check-collect-plan-impl.md`
- `../../../docs/plans/2026-03-31-database-model-redesign.md`

## Requirements

### Requirement: Integrity reports must preserve generation filters

Integrity reports SHALL store the filters used to generate missing-data results as a snapshot.

#### Scenario: Creating an integrity report
- **WHEN** a user creates an integrity report
- **THEN** the report SHALL store the stock scope, selected symbols, data types, frequency, and date range used for generation
- **AND** later edits to UI filters SHALL NOT change the saved report snapshot

### Requirement: Integrity items must represent selectable missing units

Integrity report items SHALL represent missing units that can be selected for repair.

#### Scenario: Missing period is found
- **WHEN** completeness checking finds a missing stock/data-type/period unit
- **THEN** the backend SHALL create a pending integrity item for that missing unit

#### Scenario: User selects missing items
- **WHEN** a user selects report items for repair
- **THEN** selection state SHALL be persisted before repair-plan generation

### Requirement: Repair plans must group selected items into collect jobs

Repair-plan generation SHALL create a CollectPlan and one or more CollectJobs from selected missing items.

#### Scenario: Generating a repair plan
- **WHEN** a user generates a plan from selected report items
- **THEN** the backend SHALL group items by data type and compatible parameters
- **AND** it SHALL create jobs whose config identifies the symbols and date range to repair

#### Scenario: No items are selected
- **WHEN** a user requests repair-plan generation without selected items
- **THEN** the backend SHALL reject the request with a validation error

### Requirement: Successful repair must update integrity item status

After a repair plan succeeds, related integrity items SHALL be marked fixed.

#### Scenario: Repair plan completes successfully
- **WHEN** every job in a repair plan succeeds
- **THEN** the linked selected integrity items SHALL be marked fixed
- **AND** the plan SHALL be marked completed

#### Scenario: Repair plan fails
- **WHEN** any job in a repair plan fails
- **THEN** the plan SHALL be marked failed
- **AND** related pending integrity items SHALL remain available for retry

### Requirement: Large reports must use server-side pagination

Integrity report and collect plan list/detail APIs SHALL avoid loading large result sets into frontend memory for filtering or pagination.

#### Scenario: Viewing many collect plans
- **WHEN** a user filters collect plans by source, status, or trigger type
- **THEN** the backend SHALL apply filters and pagination server-side
- **AND** the frontend SHALL use backend `count` and page metadata for pagination controls

#### Scenario: Viewing report details
- **WHEN** a report contains many integrity items
- **THEN** detail APIs SHALL return a bounded page of items
- **AND** frontend filtering SHALL not require all items to be loaded at once
