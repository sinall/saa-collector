## Why

Long-running financial statement jobs can leave Django's MySQL connection idle for many hours while collection work uses external APIs and direct MySQL connector calls. When the job finishes, plan finalization can reuse a stale Django connection and fail with `MySQL Connection not available`.

## What Changes

- Refresh Django database connections before plan finalization ORM reads and writes after job execution.
- Refresh Django database connections before job final status updates after collection work.
- Refresh connections before exception recovery writes so failure marking can use a new connection.
- Preserve existing collection behavior and task status semantics.

## Capabilities

### New Capabilities

### Modified Capabilities

- `collector-task-execution`: Long-running task finalization must not depend on stale Django database connections.

## Impact

- `collect_plan_executor` connection lifecycle around long-running job and plan finalization.
- Tests/validation for connection refresh calls where practical.
