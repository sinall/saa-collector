## Overview

Keep resume state at the collect-job level and apply it in the executor before calling symbol-loop service methods. For data types that can be safely split into single-symbol service calls, the executor will initialize `remaining_symbols`, call the service for one symbol at a time, and mark each symbol successful only after that service call returns.

## Scope

Enable symbol resume for:

- `stock_info`
- `balance_sheet`
- `income`
- `cash_flow`
- `dividend`
- `capital`
- `main_business`

Keep unchanged:

- `financial_statements`, because it already has specialized composite resume.
- `quote`, because latest quote is a bulk API call followed by local filtering.
- `historical_quote`, pending a separate design because provider implementations differ and may be date/batch oriented.
- `trade_days`, `valuation`, and `tick`, because they are not natural symbol-loop collectors in the current executor.

## Runtime Flow

1. Build and scope symbols for the data type.
2. Initialize `remaining_symbols` from requested symbols or existing resume state.
3. For each remaining symbol, call the existing service method with a one-symbol list.
4. On success, remove that symbol from `remaining_symbols`.
5. On failure, keep that symbol in `remaining_symbols`, add it to `failed_symbols`, and continue to later symbols.
6. If any symbol failed, raise a job-level error after the loop so the job and plan are marked failed.
7. If all symbols succeed, clear resume fields.

## Tests

Add focused executor tests using mocked services to verify a newly supported data type:

- Starts with all requested symbols and skips completed symbols on retry.
- Removes successful symbols and preserves failed symbols.
- Does not call service when `remaining_symbols` is empty.
