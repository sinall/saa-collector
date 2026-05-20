# Collector Testing Specification

## Purpose

Define testing expectations for collector backend, frontend, and documentation-driven changes.

Related docs:
- `../../../AGENTS.md`
- `../../../docs/testing.md`
- `../../../docs/playwright-setup.md`

## Requirements

### Requirement: Behavior changes must follow TDD

Bug fixes and feature changes SHALL add or update tests before implementation.

#### Scenario: Backend behavior changes
- **WHEN** backend collection, scheduling, API, or service behavior changes
- **THEN** a focused Django/Python test SHALL be added or updated first
- **AND** the test SHALL fail before the implementation change when practical

#### Scenario: Frontend behavior changes
- **WHEN** frontend page behavior changes
- **THEN** a Playwright or type-level regression SHALL be added or updated first
- **AND** the relevant page flow SHALL be covered

### Requirement: Frontend changes must be type-checked

Collector frontend changes SHALL pass TypeScript type checking.

#### Scenario: Vue or TypeScript files change
- **WHEN** frontend source files change
- **THEN** `npm run type-check` SHALL pass before completion

### Requirement: User-facing page changes must be covered by Playwright

Collector page-level workflows SHALL be validated with Playwright.

#### Scenario: Existing page workflow changes
- **WHEN** Dashboard, integrity report, data browse, collect plan, schedule, or instant collect workflows change
- **THEN** the corresponding `frontend/e2e/pages/*.spec.ts` coverage SHALL be updated
- **AND** `npm run test:e2e:chromium` SHALL pass unless an environment dependency is explicitly unavailable

### Requirement: Documentation-only changes must validate OpenSpec where applicable

OpenSpec and documentation reorganization SHALL validate specs and avoid stale active-task checklists.

#### Scenario: OpenSpec specs are added or modified
- **WHEN** files under `openspec/specs/` change
- **THEN** `openspec validate --specs --strict` SHALL be run from the collector repository

#### Scenario: Historical docs contain unchecked implementation tasks
- **WHEN** historical plan documents retain old checklist items
- **THEN** the document or docs index SHALL clearly mark those checklists as historical, superseded, completed, deferred, or not-current
