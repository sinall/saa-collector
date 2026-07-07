# AGENTS.md

## Project Overview

This is a SAA (Strategic Asset Allocation) Collector project with a Vue 3 frontend and Django backend.

## AI Agent Database Access

When an AI agent needs database data or runs Django commands/tests that require
a database, use the parent repository helper from `saa-parent`, not the local
development `.env` defaults:

```bash
cd ..
python3 scripts/db_query.py saa tables
python3 scripts/db_query.py saa describe saa_price_adjust_factors
python3 scripts/db_query.py saa query "SELECT COUNT(*) AS count FROM saa_price_adjust_factors"
PYENV_VERSION=collector-env python3 scripts/db_query.py saa exec \
  --cwd saa-collector/backend \
  --django-settings-module config.settings.development \
  -- pyenv exec python manage.py test saa_collector.tests.test_data_types_config
```

- The development database host, user, password, and port come from
  `saa-conf/ansible/group_vars/dev/vault.yml`.
- Do not manually decrypt the vault, print credentials, export passwords in the
  shell, or put a full connection string in logs, files, commands, or replies.
- Do not fall back to `localhost:3306` for agent-run tests or diagnostics; use
  `scripts/db_query.py saa exec` so `DATABASE_*` is injected from the
  development vault into the child process.
- The helper uses the development/public database endpoint reachable from a
  developer machine. Do not SSH through production servers or use production
  internal database addresses for agent investigation.
- Detailed rules and setup live in
  `../docs/operations/ai-database-query.md`.

## AI Agent Codegraph

When investigating cross-file dependencies, backend/frontend API impact, data completeness flow, collect plan execution, cache invalidation, or data type configuration impact, generate the parent-level lightweight codegraph first:

```bash
cd .. && just codegraph saa-collector
```

- Read `.codegraph/saa-collector.md` for the summary and high-degree files.
- Use `.codegraph/saa-collector.json` for structured dependency lookup.
- Use `.codegraph/saa-collector.dot` for optional Graphviz rendering.
- The output is local generated data and is not committed by default.
- Regenerate it manually after relevant source changes; it does not update automatically.
- To refresh it automatically after local commits, run `cd .. && just install-codegraph-hooks saa-collector`.

## Development Workflow

### TDD Principles (Test-Driven Development) ⚠️ MANDATORY

When fixing bugs or adding features, **ALWAYS follow TDD**:

1. **🔴 Red - Write a failing test first**
   - Add test case to reproduce the issue
   - Run test to confirm it fails
   - Document the expected behavior
   - Example: `frontend/e2e/pages/*.spec.ts`

2. **🟢 Green - Make the test pass**
   - Write minimal code to fix the issue
   - Run test to confirm it passes
   - Don't over-engineer the solution

3. **🔵 Refactor - Improve code quality**
   - Clean up the code
   - Ensure all tests still pass
   - Follow best practices

4. **✅ Validate - Run full test suite**
   - Run all Playwright tests
   - Check for regressions
   - Review test coverage

### Frontend Error Fixing Process (TDD Workflow)

When encountering frontend page errors, follow this process:

1. **Identify the Error**
   - Check browser console for JavaScript errors
   - Note the error message and stack trace
   - Identify the affected component/file

2. **🔴 Red - Write Failing Test**
   - Create or update test in `frontend/e2e/pages/*.spec.ts`
   - Test should reproduce the error
   - Run: `npx playwright test --project=chromium`
   - Verify test fails as expected

3. **🟢 Green - Fix the Error**
   - Locate the problematic code
   - Apply the minimal fix
   - Ensure type safety (check for null/undefined values)
   - Run: `npx playwright test --project=chromium`
   - Verify test now passes

4. **✅ Validate - Full Test Suite**
   - Run: `npm run test:e2e`
   - Check for any failed tests
   - Review screenshots and videos in `test-results/`
   - Fix any issues found
   - Re-run tests until all pass

### Why Use Playwright for Validation?

- **Automated Testing**: Catches errors you might miss manually
- **Consistency**: Same test every time
- **Speed**: Tests all pages in ~40 seconds
- **Documentation**: Screenshots and videos of failures
- **Confidence**: Know your fix didn't break anything else

## Testing

### Run Tests
```bash
# All tests
cd frontend
npm run test:e2e

# UI mode (recommended for development)
npm run test:e2e:ui

# Specific browser
npm run test:e2e:chromium

# View test report
npm run test:e2e:report
```

### Test Coverage
- Dashboard page
- Integrity Reports (list and detail)
- Data Browse (stock and type)
- Collect Plans (list and detail)
- Collect Schedules (list and detail)

## Frontend Architecture

- **Framework**: Vue 3 + TypeScript
- **UI Library**: Element Plus
- **Data Grid**: AG Grid
- **Build Tool**: Vite
- **Testing**: Playwright
- **State Management**: Composables (useDataTypes for global data type management)

## Data Type Configuration Architecture

### Overview

The project uses a **configuration-driven architecture** for managing data types. This ensures a single source of truth and eliminates hardcoded data type definitions across the codebase.

### Key Components

#### 1. Backend Configuration (Single Source of Truth)
**File**: `backend/saa_collector/constants.py`

All data type configurations are defined in `DATA_TYPE_CONFIG`:
```python
DATA_TYPE_CONFIG = {
    'trade_days': {
        'table': 'saa_trade_days',
        'label': '交易日',
        'group': 'market',
        'show_completeness': False,
        'order': 1,
        # ... more fields
    },
    # ... more data types
}
```

#### 2. Backend API
**Endpoint**: `GET /api/data-types/`

Returns all data type configurations to the frontend:
```json
{
  "data_types": [...],
  "groups": [...]
}
```

#### 3. Frontend Global State Management
**File**: `frontend/src/composables/useDataTypes.ts`

Provides centralized data type management:
```typescript
export function useDataTypes() {
  const { dataTypes, loadDataTypes, getLabel } = useDataTypes()

  // Load once on app startup
  await loadDataTypes()
}
```

#### 4. Frontend Initialization
**File**: `frontend/src/App.vue`

Preloads data type configuration on app mount:
```typescript
const { loadDataTypes } = useDataTypes()

onMounted(async () => {
  await loadDataTypes()
})
```

### Usage Examples

#### In Components
```typescript
import { useDataTypes } from '@/composables/useDataTypes'

const { dataTypes, getLabel, completenessTypes } = useDataTypes()

onMounted(async () => {
  await loadDataTypes()
  // Use dataTypes.value or completenessTypes.value
})
```

### Benefits

1. **Single Source of Truth**: All data type configurations come from one place
2. **Zero Duplication**: No more hardcoded data type lists in multiple files
3. **Type Safety**: TypeScript interfaces ensure consistency
4. **Easy Maintenance**: Adding a new data type requires only one file change
5. **Automatic Updates**: All components automatically reflect configuration changes

### Adding a New Data Type

To add a new data type, only modify `backend/saa_collector/constants.py`:

```python
'new_data_type': {
    'table': 'saa_new_data',
    'label': '新数据类型',
    'group': 'other',
    'show_completeness': True,
    'order': 16,
    # ... other required fields
}
```

All frontend components will automatically display and handle the new data type without any code changes.

## Backend Architecture

- **Framework**: Django
- **API**: Django REST Framework
- **Database**: PostgreSQL (configured via Docker)

## Code Style

- Use TypeScript for type safety
- Check for null/undefined values before accessing properties
- Use optional chaining (`?.`) when appropriate
- Provide default values for reactive refs
- No trailing whitespace in any lines
- No blank lines with spaces

## Code Review Checklist

After making any code changes, ALWAYS perform these checks:

### 1. Trailing Whitespace Check
```bash
cd frontend && git diff --check
```
- No trailing whitespace in any lines
- No blank lines with spaces

### 2. Type Check
```bash
cd frontend && npm run type-check
```
- No TypeScript errors

### 3. Lint Check (if configured)
```bash
cd frontend && npm run lint
```
- No linting errors

### 4. Test Validation
```bash
cd frontend && npm run test:e2e:chromium
```
- All tests pass

### Quick Fix for Whitespace Issues
If `git diff --check` reports trailing whitespace:
1. Open the reported file(s)
2. Go to the reported line number(s)
3. Remove all spaces/tabs on blank lines
4. Re-run `git diff --check` to verify

## Common Issues

### Null Reference Errors
Always initialize refs with default values:
```typescript
// ❌ Bad
const schedule = ref(null)

// ✅ Good
const schedule = ref<Schedule | null>(null)
// And check before accessing
if (schedule.value) {
  // safe to access schedule.value.enabled
}
```

### Element Plus Components
When using Element Plus components with conditional rendering, ensure data exists:
```vue
<!-- ❌ Bad -->
<el-switch v-model="schedule.enabled" />

<!-- ✅ Good -->
<el-switch v-if="schedule" v-model="schedule.enabled" />
```

## Mock Data

This project uses mock data for development. Mock API functions are in `frontend/src/utils/api.ts`.

When adding new features:
1. Create mock data generators
2. Create mock API functions
3. Use in development
4. Switch to real API when backend is ready
