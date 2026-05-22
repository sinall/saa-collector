## Overview

Add a data-type-level security scope rather than hardcoding financial statement filtering inside resume logic. This keeps the rule attached to the semantic data type: financial statements, statement subtypes, dividend, capital, and main business data only apply to A-share stocks.

## Decisions

- Use `security_scope: a_stock` in `DATA_TYPE_CONFIG`.
- Apply the scope in collect plan execution before progress initialization and before invoking service methods.
- Resolve explicit symbol lists by intersecting them with `saa_stocks WHERE type='STOCK' AND market='A'`.
- When no symbols are provided, keep using the existing A-stock query path.
- Do not scope quote/historical quote data because ETFs and other securities can have quote data.

## Failure Behavior

If filtering drops all symbols, the existing financial statement path treats it as no remaining work and completes without external API calls. Logs identify dropped symbols so bad schedule configuration remains visible.

## Tests

- Explicit financial statement symbols are filtered before `produce()`.
- The database-backed symbol filter uses `type='STOCK' AND market='A'` and closes DB resources.
