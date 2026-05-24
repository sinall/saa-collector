## Why

Only the composite `financial_statements` job currently persists symbol-level resume progress. Other symbol-loop collectors such as capital, dividend, statement subtypes, main business, and stock info can still restart from the beginning after worker loss.

## What Changes

- Extend symbol-level resume progress to additional collectors that naturally execute one symbol at a time.
- Reuse `remaining_symbols` and `failed_symbols` fields in `CollectJob.config`.
- Keep quote/latest-price and non-symbol jobs unchanged.
- Keep financial statement composite behavior unchanged.

## Capabilities

### New Capabilities

### Modified Capabilities

- `collector-task-execution`: Symbol-loop collectors beyond financial statements support persisted resume progress.

## Impact

- `collect_plan_executor` gains a reusable symbol-resumable execution helper.
- Statement subtype, dividend, capital, main business, and stock info execution paths call service methods per symbol with progress updates.
- Tests cover resume behavior for at least one newly supported symbol-loop collector.
