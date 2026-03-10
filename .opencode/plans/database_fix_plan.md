# Database Table Fix Plan

## Problem Summary

Multiple database tables referenced in the code don't exist, causing errors:
- `collector_collect_job` table missing (Django model without migrations)
- Table name mismatches in `DataStatusView`

## Solution

### 1. Create `collector_collect_job` Table

Execute the following SQL:

```sql
CREATE TABLE collector_collect_job (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    data_type VARCHAR(50) NOT NULL,
    symbols JSON,
    params JSON,
    status VARCHAR(20) DEFAULT 'PENDING',
    start_time DATETIME NULL,
    end_time DATETIME NULL,
    message TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_data_type (data_type),
    INDEX idx_created_at (created_at)
);
```

### 2. Update Table Mappings in `DataStatusView`

**File:** `backend/saa_collector/views.py`

#### 2.1 Update `data_types` list (lines 37-48)

Replace the existing `data_types` list with:

```python
data_types = [
    ('stock_info', '股票基本信息', 'saa_stocks'),
    ('quote', '最新行情', 'saa_latest_prices'),
    ('historical_quote', '历史行情', 'saa_prices'),
    ('balance_sheet', '资产负债表', 'saa_raw_balance_sheet'),
    ('income', '利润表', 'saa_raw_income_statement'),
    ('cash_flow', '现金流量表', 'saa_raw_cash_flow_statement'),
    ('dividend', '分红数据', 'saa_dividends'),
    ('main_business', '主营业务', 'saa_raw_main_business'),
    ('capital', '股本变动', 'saa_capitals'),
]
```

#### 2.2 Update `_get_date_column` method (lines 87-99)

Replace the existing `_get_date_column` method with:

```python
def _get_date_column(self, table_name):
    date_columns = {
        'saa_stocks': None,
        'saa_latest_prices': 'date',
        'saa_prices': 'date',
        'saa_raw_balance_sheet': 'date',
        'saa_raw_income_statement': 'date',
        'saa_raw_cash_flow_statement': 'date',
        'saa_dividends': 'date',
        'saa_raw_main_business': 'date',
        'saa_capitals': 'date',
    }
    return date_columns.get(table_name)
```

## Table Mapping Summary

| Data Type | Display Name | Table Name | Date Column |
|-----------|--------------|------------|-------------|
| stock_info | 股票基本信息 | saa_stocks | None |
| quote | 最新行情 | saa_latest_prices | date |
| historical_quote | 历史行情 | saa_prices | date |
| balance_sheet | 资产负债表 | saa_raw_balance_sheet | date |
| income | 利润表 | saa_raw_income_statement | date |
| cash_flow | 现金流量表 | saa_raw_cash_flow_statement | date |
| dividend | 分红数据 | saa_dividends | date |
| main_business | 主营业务 | saa_raw_main_business | date |
| capital | 股本变动 | saa_capitals | date |

## Changes Removed

- Removed `valuation` data type (no corresponding table)

## Execution Steps

1. Connect to MySQL database `saa`
2. Execute the `CREATE TABLE` SQL for `collector_collect_job`
3. Update `backend/saa_collector/views.py` with the new table mappings
4. Restart the Django application
5. Test the `/api/collect/jobs/` and `/api/data-status/` endpoints
