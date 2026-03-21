# AGENTS.md

## Project Overview

This is a SAA (Strategic Asset Allocation) Collector project with a Vue 3 frontend and Django backend.

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
