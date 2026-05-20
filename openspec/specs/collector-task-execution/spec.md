# Collector Task Execution Specification

## Purpose

Define how SAA Collector creates, queues, executes, resumes, and observes collection work.

Related docs:
- `../../../docs/plans/2026-03-14-integrity-check-and-collect-plan-design.md`
- `../../../docs/plans/2026-05-16-collection-progress-eta-design.md`
- `../../../docs/plans/development-backlog.md`

## Requirements

### Requirement: API processes must enqueue heavy collector work

The collector API service SHALL create and enqueue collection work instead of running heavy collection tasks inside request-handling processes.

#### Scenario: Manual plan execution
- **WHEN** a user executes a collect plan through the API
- **THEN** the API SHALL mark the plan queued and dispatch a Celery task
- **AND** the API SHALL return without running the collection workload in the web process

#### Scenario: Manual schedule trigger
- **WHEN** a user manually triggers a collection schedule
- **THEN** the API SHALL create the associated plan and jobs
- **AND** it SHALL dispatch the plan to the collector queue for worker execution

### Requirement: Beat and scheduler must not execute business collection workloads

The beat process SHALL only wake scheduler scanning, and the scheduler worker SHALL only create due plans and dispatch collector work.

#### Scenario: Periodic schedule scan
- **WHEN** the beat interval fires
- **THEN** beat SHALL enqueue `scan_due_collect_schedules` to the scheduler queue
- **AND** beat SHALL NOT query external data sources or persist business collection data

#### Scenario: Due schedule exists
- **WHEN** scheduler scanning finds an enabled due schedule
- **THEN** scheduler SHALL create the corresponding collect plan and jobs
- **AND** scheduler SHALL dispatch plan execution to the collector queue

### Requirement: Collector workers must execute business collection tasks

Collector workers SHALL consume collector queue tasks, run collection workloads, and update plan/job status.

#### Scenario: Worker receives a collect plan task
- **WHEN** a collector worker receives a collect plan task
- **THEN** it SHALL execute the plan jobs and update plan/job status
- **AND** logs SHALL include task id, plan id, job id, data type, and progress context where available

#### Scenario: Business execution fails
- **WHEN** a collect plan fails due to an exception or task loss
- **THEN** the job and plan SHALL record failure state
- **AND** the Celery task SHALL fail instead of reporting success for failed business execution

### Requirement: Long financial statement jobs must support resume progress

Full-market financial statement collection SHALL persist symbol-level progress so reruns can skip completed symbols.

#### Scenario: Starting a financial statement job
- **WHEN** a financial statement job starts
- **THEN** it SHALL initialize `remaining_symbols` from the requested symbol set
- **AND** it SHALL remove each symbol from `remaining_symbols` only after that symbol has completed collection and processing

#### Scenario: Worker is interrupted during a long job
- **WHEN** a worker restart or task loss leaves a plan/job in `RUNNING`
- **THEN** collector cleanup SHALL mark orphan running work failed
- **AND** it SHALL preserve `job.config.remaining_symbols` for retry

#### Scenario: Retrying an interrupted financial statement job
- **WHEN** a failed financial statement job is executed again
- **THEN** it SHALL process only `remaining_symbols`
- **AND** it SHALL clear progress fields after all remaining symbols succeed

### Requirement: Long job progress must be observable from logs

Long-running symbol-based collectors SHALL emit progress logs that estimate completion and expose stalled local processing.

#### Scenario: A symbol completes
- **WHEN** a symbol-level unit finishes
- **THEN** logs SHALL include completed/total count, elapsed time, average time per symbol, remaining estimate, and ETA

#### Scenario: A single-symbol job runs
- **WHEN** total work contains only one symbol
- **THEN** progress logging MAY suppress noisy `[1/1]` logs

### Requirement: Explicit chunk jobs are deferred

Chunking a single collect job into multiple Celery tasks SHALL remain a deferred enhancement unless production evidence shows renewed memory growth, unrecoverable long-task failures, or a need for batch-level retry/visibility.

#### Scenario: Worker memory remains stable
- **WHEN** full-market financial statement collection runs with stable worker memory and resumable progress
- **THEN** implementation SHALL keep the current plan/job model
- **AND** it SHALL NOT introduce user-visible chunk management

#### Scenario: Chunking becomes necessary
- **WHEN** chunking is introduced
- **THEN** chunk state SHALL be an internal execution detail
- **AND** user-visible management SHALL remain at CollectPlan and CollectJob level
