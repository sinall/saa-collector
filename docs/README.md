# SAA Collector Documentation

This directory contains collector documentation. Current durable behavior belongs in `../openspec/specs/`; `docs/` keeps operational notes, testing guides, historical designs, and backlog records.

## Current References

| Document | Purpose | Status |
| --- | --- | --- |
| `deployment.md` | Collector routing, service modes, environment, and deployment notes | Current operations reference; production Compose details still come from `../saa-conf` in the parent workspace |
| `mfactor-data-dependencies.md` | mfactor data dependency map and collector evolution boundary | Current integration/evolution reference |
| `testing.md` | E2E testing workflow and Playwright usage | Current testing reference |
| `playwright-setup.md` | Playwright system dependency setup | Current setup quick reference |
| `plans/development-backlog.md` | Rolling issue backlog from production and daily use | Current backlog |

## OpenSpec Boundary

Use `../openspec/specs/` for current rules:

- task execution, Celery roles, resume behavior, progress logging
- data type configuration and completeness behavior
- integrity reports, repair plans, and schedule-triggered plans
- external API rate limiting and future cache constraints
- deployment/auth expectations owned by collector
- testing expectations

Use `docs/plans/` for historical design notes, implementation plans, and investigation context. A historical plan can still be useful background, but unchecked tasks in those files are not automatically active work.

## Historical Plans

| Document | Status | Current Spec |
| --- | --- | --- |
| `plans/2026-03-08-django-vue-integration-design.md` | Historical foundation design | `collector-deployment-auth`, `collector-testing` |
| `plans/2026-03-14-integrity-check-and-collect-plan-design.md` | Historical design with current concepts | `collector-integrity-repair`, `collector-schedules`, `collector-task-execution` |
| `plans/2026-03-14-integrity-check-collect-plan-impl.md` | Historical implementation plan | `collector-integrity-repair` |
| `plans/2026-03-24-completeness-calculator-design.md` | Historical design; rules retained | `collector-data-configuration` |
| `plans/2026-03-31-database-model-redesign.md` | Historical completed redesign rationale | `collector-integrity-repair` |
| `plans/2026-04-03-data-type-configuration-refactoring.md` | Historical plan; implementation now exists | `collector-data-configuration` |
| `plans/2026-04-05-instant-collect-feature.md` | Historical implementation plan | `collector-schedules` |
| `plans/2026-04-13-ucenter-login-integration.md` | Historical implementation plan with current auth rules | `collector-deployment-auth` |
| `plans/2026-05-16-collection-progress-eta-design.md` | Historical design with current runtime rules | `collector-task-execution`, `collector-external-api` |
| `plans/2026-05-19-external-api-cache-design-notes.md` | Future enhancement notes; not implemented | `collector-external-api` |

## Maintenance Rules

1. Add or update OpenSpec specs when a rule should remain true after the immediate task.
2. Add operational commands, raw observations, and one-off investigation details to `docs/`.
3. Keep `plans/development-backlog.md` limited to active or recently resolved issues.
4. When a historical plan is superseded, update this index or the plan header so it cannot be mistaken for active work.
