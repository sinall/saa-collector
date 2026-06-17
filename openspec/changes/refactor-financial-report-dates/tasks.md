## Implementation Tasks

- [x] Add migration SQL for raw statement and main-business date semantic columns.
- [x] Update table configuration and Tushare statement mapping to write `report_date` and `disclosure_date`.
- [x] Update statement save, maintenance, browsing, completeness, and readiness code paths to use `report_date`.
- [x] Update collector-owned derived SQL views to expose `report_date` and `disclosure_date`, with any deliberate compatibility aliases documented in SQL.
- [x] Add or update focused backend tests for migration SQL, Tushare date mapping, and report-date based reads.
- [ ] Run OpenSpec validation and targeted backend tests.
