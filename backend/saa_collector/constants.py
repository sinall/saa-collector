"""
全局数据类型配置

这是数据类型配置的单一数据源（Single Source of Truth）。
所有数据类型相关的配置都从这里派生。

配置字段说明：
- table: 数据库表名
- date_column: 日期列名
- data_frequency: 数据更新频率 (daily/weekly/monthly/quarterly/yearly/None)
- completeness_model: 完整度热力图计算模型 (calendar/snapshot_security/periodic_security/trading_day_security/event_security/non_stock_periodic)
- stock_level: 是否按股票级别检查数据完整性
- label: 中文显示名称
- stock_column: 股票代码列名（默认为 'symbol'）
- supports_integrity_check: 是否支持完整性报告检查（非股票级别数据需要特殊处理）
- group: 所属分组（market/statement/other/valuation/industry）
- show_completeness: 是否在仪表盘显示完整性
- need_date: 采集时是否需要日期参数
- date_anchor: 默认日期锚点策略（如 execution_day/month_end_trade_day）
- security_scope: 证券范围约束（如 'a_stock' 表示仅 A 股股票）
- visibility: 不同业务上下文中的可见性（collect/collect_plan/schedule/data_check/integrity_report/dashboard）
- order: 排序序号（越小越靠前）
"""

DATA_TYPE_VISIBILITY_CONTEXTS = (
    'collect',
    'collect_plan',
    'schedule',
    'data_check',
    'integrity_report',
    'dashboard',
)


def is_data_type_visible(data_type: str, context: str) -> bool:
    config = DATA_TYPE_CONFIG.get(data_type, {})
    visibility = config.get('visibility') or {}
    if context in visibility:
        return bool(visibility[context])

    return True

DATA_TYPE_CONFIG = {
    'tick': {
        'table': None,
        'date_column': None,
        'data_frequency': None,
        'stock_level': False,
        'label': '定时心跳',
        'supports_integrity_check': False,
        'group': 'other',
        'show_completeness': False,
        'visibility': {
            'collect': False,
            'collect_plan': False,
            'data_check': False,
            'integrity_report': False,
            'dashboard': False,
            'schedule': True,
        },
        'need_date': False,
        'order': 0,
    },
    'trade_days': {
        'table': 'saa_trade_days',
        'date_column': 'date',
        'data_frequency': 'daily',
        'completeness_model': 'calendar',
        'stock_level': False,
        'label': '交易日',
        'supports_integrity_check': True,
        'group': 'market',
        'show_completeness': False,
        'need_date': True,
        'order': 1,
    },
    'stock_info': {
        'table': 'saa_stocks',
        'date_column': None,
        'data_frequency': None,
        'completeness_model': 'snapshot_security',
        'stock_level': False,
        'label': '股票基本信息',
        'supports_integrity_check': False,
        'group': 'market',
        'show_completeness': False,
        'need_date': False,
        'order': 2,
    },
    'securities': {
        'table': 'saa_securities',
        'date_column': None,
        'data_frequency': None,
        'completeness_model': 'snapshot_security',
        'stock_level': True,
        'label': '证券主数据',
        'stock_column': 'code',
        'supports_integrity_check': False,
        'group': 'market',
        'show_completeness': False,
        'need_date': False,
        'security_scope': 'a_stock',
        'order': 3,
    },
    'quote': {
        'table': 'saa_latest_prices',
        'date_column': None,
        'data_frequency': 'daily',
        'completeness_model': 'snapshot_security',
        'stock_level': True,
        'label': '最新行情',
        'supports_integrity_check': True,
        'group': 'market',
        'show_completeness': True,
        'need_date': False,
        'order': 3,
    },
    'historical_quote': {
        'table': 'saa_prices_ex',
        'date_column': 'date',
        'data_frequency': 'monthly',
        'date_anchor': 'month_end_trade_day',
        'completeness_model': 'periodic_security',
        'stock_level': True,
        'label': '历史行情',
        'stock_column': 'code',
        'supports_integrity_check': True,
        'group': 'market',
        'show_completeness': True,
        'need_date': True,
        'order': 4,
    },
    'price_adjust_factor': {
        'table': 'saa_price_adjust_factors',
        'date_column': 'date',
        'data_frequency': 'monthly',
        'date_anchor': 'month_end_trade_day',
        'completeness_model': 'periodic_security',
        'stock_level': True,
        'label': '复权因子',
        'stock_column': 'code',
        'supports_integrity_check': True,
        'group': 'market',
        'show_completeness': True,
        'need_date': True,
        'order': 5,
    },
    'extras': {
        'table': 'saa_extras',
        'date_column': 'date',
        'data_frequency': 'daily',
        'completeness_model': 'trading_day_security',
        'stock_level': True,
        'label': '股票状态',
        'stock_column': 'code',
        'supports_integrity_check': True,
        'group': 'market',
        'show_completeness': True,
        'need_date': True,
        'security_scope': 'a_stock',
        'order': 6,
    },
    'index_quotes': {
        'table': 'saa_index_quotes',
        'date_column': 'date',
        'data_frequency': 'daily',
        'completeness_model': 'non_stock_periodic',
        'stock_level': False,
        'label': '指数行情',
        'supports_integrity_check': True,
        'group': 'market',
        'show_completeness': True,
        'need_date': True,
        'order': 6,
    },
    'financial_statements': {
        'table': None,
        'date_column': None,
        'data_frequency': 'quarterly',
        'completeness_model': None,
        'stock_level': False,
        'label': '财务报表(三表+分红)',
        'composite': True,
        'sub_types': ['balance_sheet', 'income', 'cash_flow', 'dividend'],
        'supports_integrity_check': False,
        'group': 'statement',
        'show_completeness': False,
        'need_date': True,
        'security_scope': 'a_stock',
        'order': 7,
    },
    'balance_sheet': {
        'table': 'saa_raw_balance_sheet',
        'date_column': 'report_date',
        'data_frequency': 'quarterly',
        'completeness_model': 'periodic_security',
        'stock_level': True,
        'label': '资产负债表',
        'supports_integrity_check': True,
        'group': 'statement',
        'show_completeness': True,
        'need_date': True,
        'security_scope': 'a_stock',
        'order': 8,
    },
    'income': {
        'table': 'saa_raw_income_statement',
        'date_column': 'report_date',
        'data_frequency': 'quarterly',
        'completeness_model': 'periodic_security',
        'stock_level': True,
        'label': '利润表',
        'supports_integrity_check': True,
        'group': 'statement',
        'show_completeness': True,
        'need_date': True,
        'security_scope': 'a_stock',
        'order': 9,
    },
    'cash_flow': {
        'table': 'saa_raw_cash_flow_statement',
        'date_column': 'report_date',
        'data_frequency': 'quarterly',
        'completeness_model': 'periodic_security',
        'stock_level': True,
        'label': '现金流量表',
        'supports_integrity_check': True,
        'group': 'statement',
        'show_completeness': True,
        'need_date': True,
        'security_scope': 'a_stock',
        'order': 10,
    },
    'main_business': {
        'table': 'saa_raw_main_business',
        'date_column': 'report_date',
        'data_frequency': 'quarterly',
        'completeness_model': 'periodic_security',
        'stock_level': True,
        'label': '主营业务',
        'supports_integrity_check': True,
        'group': 'other',
        'show_completeness': True,
        'need_date': True,
        'security_scope': 'a_stock',
        'order': 11,
    },
    'capital': {
        'table': 'saa_capitals',
        'date_column': 'date',
        'data_frequency': 'yearly',
        'completeness_model': 'periodic_security',
        'stock_level': True,
        'label': '股本变动',
        'supports_integrity_check': True,
        'group': 'other',
        'show_completeness': True,
        'need_date': True,
        'security_scope': 'a_stock',
        'order': 12,
    },
    'dividend': {
        'table': 'saa_dividends',
        'date_column': 'date',
        'data_frequency': 'yearly',
        'completeness_model': 'event_security',
        'stock_level': True,
        'label': '分红数据',
        'supports_integrity_check': True,
        'group': 'other',
        'show_completeness': True,
        'need_date': True,
        'security_scope': 'a_stock',
        'order': 13,
    },
    'valuation': {
        'table': None,
        'date_column': None,
        'data_frequency': None,
        'stock_level': False,
        'label': '估值数据',
        'supports_integrity_check': False,
        'group': 'valuation',
        'show_completeness': False,
        'need_date': False,
        'order': 14,
    },
    'valuation_board': {
        'table': 'saa_board_valuation_levels',
        'date_column': 'report_date',
        'data_frequency': 'daily',
        'completeness_model': 'non_stock_periodic',
        'stock_level': False,
        'label': '板块估值',
        'supports_integrity_check': True,
        'group': 'valuation',
        'show_completeness': True,
        'need_date': True,
        'order': 15,
    },
    'valuation_industry': {
        'table': 'saa_industry_valuation_levels',
        'date_column': 'report_date',
        'data_frequency': 'daily',
        'completeness_model': 'non_stock_periodic',
        'stock_level': False,
        'label': '行业估值',
        'supports_integrity_check': True,
        'group': 'valuation',
        'show_completeness': True,
        'need_date': True,
        'order': 16,
    },
    'index_weights': {
        'table': 'saa_index_weights',
        'date_column': 'date',
        'data_frequency': 'monthly',
        'date_anchor': 'month_end_trade_day',
        'completeness_model': 'periodic_security',
        'stock_level': True,
        'label': '指数成分股权重',
        'stock_column': 'code',
        'supports_integrity_check': True,
        'group': 'industry',
        'show_completeness': True,
        'need_date': True,
        'order': 17,
    },
    'industries': {
        'table': 'saa_industries',
        'date_column': None,
        'data_frequency': None,
        'completeness_model': 'non_stock_periodic',
        'stock_level': False,
        'label': '量化行业分类',
        'supports_integrity_check': True,
        'group': 'industry',
        'show_completeness': False,
        'need_date': False,
        'order': 18,
    },
    'csrc_industry_classifications': {
        'table': 'saa_industry_classifications',
        'date_column': None,
        'data_frequency': None,
        'stock_level': False,
        'label': '证监会行业分类',
        'supports_integrity_check': False,
        'group': 'industry',
        'show_completeness': False,
        'need_date': False,
        'order': 19,
    },
    'industry_stocks': {
        'table': 'saa_industry_stocks',
        'date_column': 'date',
        'data_frequency': 'monthly',
        'date_anchor': 'month_end_trade_day',
        'completeness_model': 'periodic_security',
        'stock_level': True,
        'label': '行业成分股',
        'stock_column': 'code',
        'supports_integrity_check': True,
        'group': 'industry',
        'show_completeness': True,
        'need_date': True,
        'order': 20,
    },
}

DATA_TYPE_GROUPS = [
    {'key': 'market', 'label': '市场数据', 'order': 1},
    {'key': 'statement', 'label': '财务报表', 'order': 2},
    {'key': 'other', 'label': '其他数据', 'order': 3},
    {'key': 'valuation', 'label': '估值数据', 'order': 4},
    {'key': 'industry', 'label': '行业相关', 'order': 5},
]

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
