## Why

Financial statement-style data is only valid for stock issuers. When collector jobs receive explicit symbol lists that include ETFs or other non-stock securities, those symbols should be filtered by data type semantics before collection starts.

## What Changes

- Add a data type security-scope rule for financial statement, dividend, capital, and main-business data types.
- Filter explicit symbol lists to A-share stocks before executing those data type collectors.
- Log when symbols are dropped by the scope filter.
- Leave quote and historical quote data unchanged because non-stock securities may have valid quote data.

## Capabilities

### New Capabilities

### Modified Capabilities

- `collector-data-configuration`: Data type configuration can constrain valid security scope for collection.

## Impact

- `DATA_TYPE_CONFIG` gains a `security_scope` field for A-stock-only data types.
- Collect plan execution applies that scope before symbol progress tracking and service calls.
- Tushare stock service provides a database-backed A-stock symbol filter.
