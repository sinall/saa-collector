## Overview

The reported failure happens after a successful 67-hour financial statement job. `execute_plan()` then calls `plan.refresh_from_db()`, but Django's MySQL connector connection is no longer usable. Because this is finalization logic, the executor should explicitly discard old Django connections before ORM operations that happen after long collection work.

## Decisions

- Use `db.connections.close_all()` before plan finalization after all jobs finish.
- Use `db.connections.close_all()` before marking a job success/failure after `execute_collect()`.
- Use `db.connections.close_all()` before exception recovery queries that mark plans or jobs failed.
- Keep service-level direct MySQL connector usage unchanged.

## Failure Behavior

If the first finalization query hits an unusable connection, explicitly closing connections before it forces Django to open a fresh connection instead of reusing the stale one. If the database is genuinely unavailable, the existing exception path still logs and raises.

## Tests

Use focused validation where possible and compile checks in the current environment. Full Django executor tests are currently blocked by missing Celery in `collector-env`.
