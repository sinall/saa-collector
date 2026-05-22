## MODIFIED Requirements

### Requirement: Collector workers must finalize long-running work using usable database connections

Collector workers SHALL avoid reusing stale Django database connections when marking long-running jobs and plans complete or failed.

#### Scenario: Long-running job finishes after hours of external work
- **WHEN** a collect job finishes after a long-running collection workload
- **THEN** the worker SHALL refresh Django database connections before writing the final job status
- **AND** it SHALL refresh Django database connections before reading and writing final plan status

#### Scenario: Long-running job or plan fails
- **WHEN** a collect job or plan enters exception recovery
- **THEN** the worker SHALL refresh Django database connections before attempting to mark the job or plan failed
