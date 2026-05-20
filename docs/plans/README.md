# Collector Plans Index

Files in this directory are historical plans, design notes, and backlog records. Current durable behavior has been extracted to `../../openspec/specs/`.

## How To Read This Directory

- `development-backlog.md` is the active rolling backlog.
- Dated plans are historical context unless their header explicitly says otherwise.
- Unchecked checklist items in historical plans are not automatically active tasks.
- New accepted requirements should be expressed in OpenSpec first, then implemented through a change.

## Current OpenSpec Map

| Topic | Spec |
| --- | --- |
| Task execution, Celery roles, resume, progress | `../../openspec/specs/collector-task-execution/spec.md` |
| Data type metadata and completeness | `../../openspec/specs/collector-data-configuration/spec.md` |
| Integrity reports and repair plans | `../../openspec/specs/collector-integrity-repair/spec.md` |
| Schedules and instant collect | `../../openspec/specs/collector-schedules/spec.md` |
| Tushare/Akshare calls, rate limiting, cache proposal | `../../openspec/specs/collector-external-api/spec.md` |
| Deployment routing and auth | `../../openspec/specs/collector-deployment-auth/spec.md` |
| Testing expectations | `../../openspec/specs/collector-testing/spec.md` |
