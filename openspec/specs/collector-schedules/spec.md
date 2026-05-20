# Collector Schedules Specification

## Purpose

Define collect schedule behavior, manual triggers, due scanning, and plan provenance.

Related docs:
- `../../../docs/plans/2026-03-14-integrity-check-and-collect-plan-design.md`
- `../../../docs/plans/2026-04-05-instant-collect-feature.md`
- `../../../docs/plans/development-backlog.md`

## Requirements

### Requirement: Schedules must create plans rather than execute collection inline

Collect schedules SHALL create collect plans and dispatch them through the task execution pipeline.

#### Scenario: Automatic due schedule
- **WHEN** an enabled schedule reaches its due time
- **THEN** scheduler scanning SHALL create a CollectPlan with associated CollectJobs
- **AND** it SHALL enqueue the plan for collector worker execution

#### Scenario: Disabled schedule reaches due time
- **WHEN** a disabled schedule reaches its due time
- **THEN** scheduler scanning SHALL skip it

### Requirement: Manually triggered schedules must preserve provenance

Manual schedule triggers SHALL return the persisted plan created from the schedule.

#### Scenario: User triggers a schedule
- **WHEN** a user clicks execute on a schedule
- **THEN** the backend SHALL create a plan with `source='SCHEDULE'`, `trigger_type='MANUAL'`, `source_schedule_id`, and `source_schedule_name`
- **AND** the frontend SHALL navigate to the returned plan id

#### Scenario: Plan list displays schedule-triggered plans
- **WHEN** the collect plan list is filtered to schedule-triggered plans
- **THEN** server-side filtering SHALL include manually and automatically triggered schedule plans according to query parameters

### Requirement: Instant collect must create executable plans

The instant collect workflow SHALL create a plan and jobs in one API request.

#### Scenario: User submits instant collect
- **WHEN** a user submits data type, symbol scope, and parameters through the instant collect dialog
- **THEN** the backend SHALL validate the requested jobs
- **AND** it SHALL create a manual CollectPlan ready for execution

#### Scenario: Instant collect is executed immediately
- **WHEN** the request asks to execute immediately
- **THEN** the backend SHALL enqueue the created plan and return queued plan metadata
