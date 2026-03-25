"""
全局数据类型配置

这是数据类型配置的单一数据源（Single Source of Truth）。
所有数据类型相关的配置都从这里派生。

配置字段说明：
- table: 数据库表名
- date_column: 日期列名
- data_frequency: 数据更新频率 (daily/weekly/monthly/quarterly/yearly/None)
- stock_level: 是否按股票级别检查数据完整性
- label: 中文显示名称
- stock_column: 股票代码列名（默认为 'symbol'）
- supports_integrity_check: 是否支持完整性报告检查（非股票级别数据需要特殊处理）
"""

DATA_TYPE_CONFIG = {
    'trade_days': {
        'table': 'saa_trade_days',
        'date_column': 'date',
        'data_frequency': 'daily',
        'stock_level': False,
        'label': '交易日',
        'supports_integrity_check': True,
    },
    'stock_info': {
        'table': 'saa_stocks',
        'date_column': None,
        'data_frequency': None,
        'stock_level': True,
        'label': '股票基本信息',
        'supports_integrity_check': False,
    },
    'quote': {
        'table': 'saa_latest_prices',
        'date_column': 'date',
        'data_frequency': 'daily',
        'stock_level': True,
        'label': '最新行情',
        'supports_integrity_check': True,
    },
    'historical_quote': {
        'table': 'saa_prices_ex',
        'date_column': 'date',
        'data_frequency': 'daily',
        'stock_level': True,
        'label': '历史行情',
        'stock_column': 'code',
        'supports_integrity_check': True,
    },
    'balance_sheet': {
        'table': 'saa_raw_balance_sheet',
        'date_column': 'date',
        'data_frequency': 'quarterly',
        'stock_level': True,
        'label': '资产负债表',
        'supports_integrity_check': True,
    },
    'income': {
        'table': 'saa_raw_income_statement',
        'date_column': 'date',
        'data_frequency': 'quarterly',
        'stock_level': True,
        'label': '利润表',
        'supports_integrity_check': True,
    },
    'cash_flow': {
        'table': 'saa_raw_cash_flow_statement',
        'date_column': 'date',
        'data_frequency': 'quarterly',
        'stock_level': True,
        'label': '现金流量表',
        'supports_integrity_check': True,
    },
    'main_business': {
        'table': 'saa_raw_main_business',
        'date_column': 'date',
        'data_frequency': 'quarterly',
        'stock_level': True,
        'label': '主营业务',
        'supports_integrity_check': True,
    },
    'capital': {
        'table': 'saa_capitals',
        'date_column': 'date',
        'data_frequency': 'yearly',
        'stock_level': True,
        'label': '股本变动',
        'supports_integrity_check': True,
    },
    'dividend': {
        'table': 'saa_dividends',
        'date_column': 'date',
        'data_frequency': 'yearly',
        'stock_level': True,
        'label': '分红数据',
        'supports_integrity_check': True,
    },
    'valuation_board': {
        'table': 'saa_board_valuation_levels',
        'date_column': 'report_date',
        'data_frequency': 'daily',
        'stock_level': False,
        'label': '板块估值',
        'supports_integrity_check': True,
    },
    'valuation_industry': {
        'table': 'saa_industry_valuation_levels',
        'date_column': 'report_date',
        'data_frequency': 'daily',
        'stock_level': False,
        'label': '行业估值',
        'supports_integrity_check': True,
    },
}

DATA_TYPE_CHOICES = [
    (key, config['label'])
    for key, config in DATA_TYPE_CONFIG.items()
]

DATA_TYPE_FREQUENCY = {
    key: config['data_frequency']
    for key, config in DATA_TYPE_CONFIG.items()
}

DATA_TYPE_LABELS = {
    key: config['label']
    for key, config in DATA_TYPE_CONFIG.items()
}

TABLE_MAPPING = {
    key: config['table']
    for key, config in DATA_TYPE_CONFIG.items()
    if config['supports_integrity_check']
}

STOCK_LEVEL_TYPES = {
    key for key, config in DATA_TYPE_CONFIG.items()
    if config['stock_level']
}

NON_STOCK_LEVEL_TYPES = {
    key for key, config in DATA_TYPE_CONFIG.items()
    if not config['stock_level']
}

QUARTERLY_TYPES = {
    key for key, config in DATA_TYPE_CONFIG.items()
    if config['data_frequency'] == 'quarterly'
}

YEARLY_TYPES = {
    key for key, config in DATA_TYPE_CONFIG.items()
    if config['data_frequency'] == 'yearly'
}

DAILY_TYPES = {
    key for key, config in DATA_TYPE_CONFIG.items()
    if config['data_frequency'] == 'daily'
}

EARLIEST_YEAR = 1990
A_STOCK_EARLIEST_DATE = '1990-12-19'
EXPECTED_A_SHARE_STOCKS = 5500
