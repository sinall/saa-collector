# Collector Deployment And Auth Specification

## Purpose

Define collector-owned deployment assumptions, routing behavior, service modes, and authentication expectations.

Related docs:
- `../../../docs/deployment.md`
- `../../../docs/plans/2026-04-13-ucenter-login-integration.md`

## Requirements

### Requirement: Production routing must preserve the collector base path

Collector production URLs SHALL be served under `/admin/collector/`.

#### Scenario: Browser requests frontend route
- **WHEN** a browser requests `/admin/collector/` or a frontend route below it
- **THEN** Nginx SHALL route the request to the collector frontend container
- **AND** the frontend SHALL serve the Vue SPA with `/admin/collector/` as its base path

#### Scenario: Browser requests API route
- **WHEN** a browser requests `/admin/collector/api/...`
- **THEN** Nginx SHALL forward the request to the Django API with the collector prefix stripped as configured

#### Scenario: Browser requests Django static assets
- **WHEN** a browser requests `/admin/collector/static/...`
- **THEN** Nginx SHALL route the request to the backend static asset handler

### Requirement: Backend service mode must be explicit

The backend entrypoint SHALL select process role from `SERVICE`.

#### Scenario: API container starts
- **WHEN** `SERVICE=gunicorn`
- **THEN** the container SHALL run Gunicorn for Django API requests

#### Scenario: Worker container starts
- **WHEN** `SERVICE=celery-worker`
- **THEN** the container SHALL run a Celery worker for its configured queue

#### Scenario: Beat container starts
- **WHEN** `SERVICE=celery-beat`
- **THEN** the container SHALL run Celery beat

### Requirement: Production API access must require authentication

Production collector APIs SHALL require authenticated access.

#### Scenario: UCenter is configured
- **WHEN** `UC_API`, `UC_KEY`, `UC_APPID`, and admin users are configured
- **THEN** login SHALL authenticate against UCenter
- **AND** only configured admin users SHALL receive collector access

#### Scenario: Development auth fallback is used
- **WHEN** UCenter is not configured in a development environment
- **THEN** the development fallback MAY allow local testing credentials
- **AND** this fallback SHALL NOT be treated as production authentication

### Requirement: Production deployment source of truth is saa-conf

Production Compose, Nginx, mounts, memory limits, and environment files SHALL be checked in `saa-conf` before drawing conclusions from collector-local examples.

#### Scenario: Investigating production service names
- **WHEN** an operator investigates production collector containers
- **THEN** they SHALL inspect `saa-conf/ansible/roles/nginx/files/docker-compose.yml`
- **AND** they SHALL treat collector-local compose files as development examples unless explicitly documented otherwise
