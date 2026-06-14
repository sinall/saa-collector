"""
完整度计算服务

提供统一的完整度计算逻辑，供仪表盘热力图和完整性报告热力图使用。
"""
import logging
import time
from datetime import date, datetime, timedelta
from django.db import connection
from calendar import monthrange

from ..constants import DATA_TYPE_CONFIG, EARLIEST_YEAR
from .common.index_scope_utils import resolve_index_constituent_payloads_by_dates, resolve_index_constituents_by_dates
from .common.period_utils import get_period_label_for_date, get_period_range

logger = logging.getLogger(__name__)


class CompletenessService:
    """完整度计算服务"""

    DATA_TYPE_CONFIG = [
        (key, config)
        for key, config in DATA_TYPE_CONFIG.items()
    ]

    def __init__(self, stock_codes=None, index_code=None, date_end=None):
        self.stock_codes = stock_codes
        self.index_code = index_code
        self.date_end = date_end or date.today()
        self._trade_days = None
        self._trade_days_range = None
        self._security_active_ranges = None
        self._security_active_ranges_range = None
        self._expected_stock_counts_cache = {}
        self._non_stock_counts_cache = {}
        self._period_anchor_trade_days_cache = {}
        self._index_constituents_cache = {}
        self._index_period_specs_cache = {}

    def _load_trade_days(self, cursor, start_date, end_date):
        start_date = self._coerce_date(start_date)
        end_date = self._coerce_date(end_date)
        if (
            self._trade_days is not None
            and self._trade_days_range is not None
            and self._trade_days_range[0] <= start_date
            and self._trade_days_range[1] >= end_date
        ):
            return [
                trade_day for trade_day in self._trade_days
                if start_date <= trade_day <= end_date
            ]

        cursor.execute(
            """
                SELECT date
                FROM saa_trade_days
                WHERE date >= %s
                  AND date <= %s
                ORDER BY date
            """,
            [start_date, end_date],
        )
        self._trade_days = [self._coerce_date(row[0]) for row in cursor.fetchall()]
        self._trade_days_range = (start_date, end_date)
        return self._trade_days

    def _load_security_active_ranges(self, cursor, start_date=None, end_date=None):
        normalized_start = self._coerce_date(start_date) if start_date else None
        normalized_end = self._coerce_date(end_date) if end_date else None
        if self._security_active_ranges is not None:
            if not normalized_start or not normalized_end:
                return self._security_active_ranges
            if (
                self._security_active_ranges_range is not None
                and self._security_active_ranges_range[0] <= normalized_start
                and self._security_active_ranges_range[1] >= normalized_end
            ):
                return [
                    row for row in self._security_active_ranges
                    if row[1] <= normalized_end and row[2] >= normalized_start
                ]

        params = []
        date_filter = ""
        if start_date and end_date:
            date_filter = """
                  AND (start_date IS NULL OR start_date <= %s)
                  AND (end_date IS NULL OR end_date >= %s)
            """
            params.extend([normalized_end, normalized_start])

        stock_filter = ""
        if self.stock_codes:
            placeholders = ','.join(['%s'] * len(self.stock_codes))
            stock_filter = f" AND code IN ({placeholders})"
            params.extend(self.stock_codes)

        cursor.execute(
            f"""
                SELECT code, start_date, end_date
                FROM saa_securities
                WHERE type = 'stock'{date_filter}{stock_filter}
            """,
            params,
        )

        self._security_active_ranges = [
            (
                code,
                self._coerce_date(security_start, date.min),
                self._coerce_date(security_end, date.max),
            )
            for code, security_start, security_end in cursor.fetchall()
        ]
        self._security_active_ranges_range = (
            normalized_start or date.min,
            normalized_end or date.max,
        )
        return self._security_active_ranges

    def _prepare_period_universe(self, cursor, data_type_configs, periods, frequency):
        if not periods:
            return

        start_date, end_date = self._get_period_range(periods[0], frequency)
        _, end_date = self._get_period_range(periods[-1], frequency)
        self._load_trade_days(cursor, start_date, end_date)

        if self.index_code:
            return

        needs_security_universe = any(
            config.get('completeness_model') in ('snapshot_security', 'trading_day_security')
            or (
                config.get('stock_level', True)
                and config.get('date_column') is not None
                and config.get('completeness_model') != 'event_security'
            )
            for _, config in data_type_configs
        )
        if needs_security_universe:
            self._load_security_active_ranges(cursor, start_date, end_date)

    def _get_period_end_date(self, period, frequency):
        """
        获取周期的结束日期

        Args:
            period: 周期字符串，如 '2009-01', '2009-Q1', '2009', '2009-01-15'
            frequency: 频率 ('daily', 'monthly', 'quarterly', 'yearly')

        Returns:
            date: 周期结束日期
        """
        if frequency == 'daily':
            return date(int(period[:4]), int(period[5:7]), int(period[8:10]))
        elif frequency == 'monthly':
            year, month = int(period[:4]), int(period[5:7])
            _, last_day = monthrange(year, month)
            return date(year, month, last_day)
        elif frequency == 'quarterly':
            year = int(period[:4])
            quarter = int(period[6])
            end_month = quarter * 3
            _, last_day = monthrange(year, end_month)
            return date(year, end_month, last_day)
        elif frequency == 'yearly':
            year = int(period)
            return date(year, 12, 31)
        return date.today()

    def _get_expected_stock_counts(self, cursor, periods, frequency):
        """
        批量获取各周期的预期股票数（基于上市时间）

        Args:
            cursor: 数据库游标
            periods: 周期列表 ['2009-01', '2009-02', ...]
            frequency: 频率 ('daily', 'monthly', 'quarterly', 'yearly')

        Returns:
            dict: {period: expected_count}
        """
        cache_key = (frequency, tuple(periods))
        if cache_key in self._expected_stock_counts_cache:
            return self._expected_stock_counts_cache[cache_key]

        if self.index_code:
            start_date, end_date = self._get_period_range(periods[0], frequency)
            _, end_date = self._get_period_range(periods[-1], frequency)
            index_constituents_by_period = self._load_index_constituents_by_period(
                cursor, periods, frequency, start_date, end_date
            )
            result = {
                period: len(index_constituents_by_period.get(period, set()))
                for period in periods
            }
            self._expected_stock_counts_cache[cache_key] = result
            return result

        start_date, end_date = self._get_period_range(periods[0], frequency)
        _, end_date = self._get_period_range(periods[-1], frequency)
        anchor_trade_days = self._get_period_anchor_trade_days(cursor, periods, frequency, start_date, end_date)
        if not anchor_trade_days:
            result = {period: 0 for period in periods}
            self._expected_stock_counts_cache[cache_key] = result
            return result

        active_ranges = self._load_security_active_ranges(cursor, start_date, end_date)
        result = self._count_active_securities_by_anchor(periods, anchor_trade_days, active_ranges)

        self._expected_stock_counts_cache[cache_key] = result
        return result

    def calculate_all(self, data_types, periods, frequency):
        """
        批量计算多个数据类型的完整度

        Args:
            data_types: 数据类型列表
            periods: 周期列表
            frequency: 显示频率

        Returns:
            {
                'date_range': {'start': str, 'end': str},
                'frequency': str,
                'periods': [...],
                'data_types': [{key, label, frequency}, ...],
                'matrix': {data_type: [values...]}
            }
        """
        data_type_configs = self._get_data_type_configs(data_types)

        matrix = {}
        with connection.cursor() as cursor:
            self._prepare_period_universe(cursor, data_type_configs, periods, frequency)

            for key, config in data_type_configs:
                started_at = time.monotonic()
                label = config['label']
                table_name = config['table']
                date_column = config['date_column']
                data_frequency = config['data_frequency']
                stock_column = config.get('stock_column', 'symbol')
                stock_level = config.get('stock_level', True)
                completeness_model = config.get('completeness_model')

                logger.info(
                    "heatmap data_type start key=%s label=%s table=%s frequency=%s periods=%s "
                    "data_frequency=%s completeness_model=%s stock_level=%s",
                    key,
                    label,
                    table_name,
                    frequency,
                    len(periods),
                    data_frequency,
                    completeness_model,
                    stock_level,
                )

                try:
                    if date_column is None:
                        if completeness_model == 'snapshot_security':
                            matrix[key] = self._calculate_snapshot_security_completeness(
                                cursor, table_name, periods, frequency, stock_column
                            )
                        else:
                            matrix[key] = [1.0] * len(periods)
                        continue

                    if completeness_model == 'event_security':
                        matrix[key] = self._calculate_event_security_completeness(
                            cursor, table_name, date_column, periods, frequency, stock_column
                        )
                        continue

                    if completeness_model == 'trading_day_security':
                        matrix[key] = self._calculate_trading_day_security_completeness(
                            cursor, config, periods, frequency
                        )
                        continue

                    if not stock_level:
                        matrix[key] = self._calculate_non_stock_completeness(cursor, table_name, date_column, periods, frequency)
                        continue

                    if data_frequency is None:
                        matrix[key] = self._calculate_point_completeness(cursor, table_name, date_column, periods, frequency, stock_column)
                        continue

                    try:
                        matrix[key] = self._calculate_completeness(
                            cursor, table_name, date_column, periods, frequency, data_frequency, stock_column
                        )
                    except Exception:
                        logger.exception("heatmap data_type failed key=%s table=%s", key, table_name)
                        matrix[key] = [0.0] * len(periods)
                finally:
                    elapsed_ms = int((time.monotonic() - started_at) * 1000)
                    values = matrix.get(key, [])
                    logger.info(
                        "heatmap data_type done key=%s table=%s frequency=%s periods=%s "
                        "values=%s elapsed_ms=%s",
                        key,
                        table_name,
                        frequency,
                        len(periods),
                        len(values),
                        elapsed_ms,
                    )

                if key not in matrix:
                    matrix[key] = [0.0] * len(periods)

        start_date = periods[0] if periods else ''
        end_date = periods[-1] if periods else ''

        return {
            'date_range': {'start': start_date, 'end': end_date},
            'frequency': frequency,
            'periods': periods,
            'data_types': [
                {
                    'key': key,
                    'label': config['label'],
                    'frequency': config.get('data_frequency'),
                    'completeness_model': config.get('completeness_model'),
                }
                for key, config in data_type_configs
            ],
            'matrix': matrix,
        }

    def generate_periods(self, frequency, start_date=None, end_date=None):
        """生成周期列表"""
        periods = []
        today = self.date_end

        if frequency == 'daily':
            start = start_date or (today - timedelta(days=365))
            current = start
            end = end_date or today
            while current <= end:
                periods.append(current.strftime('%Y-%m-%d'))
                current += timedelta(days=1)
        elif frequency == 'monthly':
            if start_date:
                year, month = start_date.year, start_date.month
            else:
                year, month = EARLIEST_YEAR, 1
            end = end_date or today
            while date(year, month, 1) <= end:
                periods.append(f"{year}-{month:02d}")
                month += 1
                if month > 12:
                    month = 1
                    year += 1
        elif frequency == 'quarterly':
            if start_date:
                year, quarter = start_date.year, (start_date.month - 1) // 3 + 1
            else:
                year, quarter = EARLIEST_YEAR, 1
            end = end_date or today
            while date(year, quarter * 3, 1) <= end:
                periods.append(f"{year}-Q{quarter}")
                quarter += 1
                if quarter > 4:
                    quarter = 1
                    year += 1
        elif frequency == 'yearly':
            if start_date:
                year = start_date.year
            else:
                year = EARLIEST_YEAR
            end = end_date or today
            while year <= end.year:
                periods.append(str(year))
                year += 1
        else:
            return None

        return periods

    def _get_data_type_configs(self, data_types):
        """获取数据类型配置"""
        config_dict = {key: (key, config) for key, config in self.DATA_TYPE_CONFIG}

        if data_types:
            return [config_dict[dt] for dt in data_types if dt in config_dict]
        return self.DATA_TYPE_CONFIG

    def _calculate_snapshot_security_completeness(self, cursor, table_name, periods, frequency, stock_column='symbol'):
        """计算证券主数据快照完整度。"""
        if not table_name:
            return [-1] * len(periods)

        expected_counts = self._get_expected_stock_counts(cursor, periods, frequency)

        if self.index_code:
            start_date, end_date = self._get_period_range(periods[0], frequency)
            _, end_date = self._get_period_range(periods[-1], frequency)
            index_constituents_by_period = self._load_index_constituents_by_period(
                cursor, periods, frequency, start_date, end_date
            )
            cursor.execute(f"SELECT DISTINCT {stock_column} FROM {table_name}")
            actual_codes = {row[0] for row in cursor.fetchall()}
            return [
                self._ratio_for_constituents(
                    actual_codes,
                    index_constituents_by_period.get(period, set()),
                    expected_counts.get(period, 0),
                )
                for period in periods
            ]

        stock_filter = ""
        params = []
        if self.stock_codes:
            placeholders = ','.join(['%s'] * len(self.stock_codes))
            stock_filter = f" WHERE {stock_column} IN ({placeholders})"
            params = self.stock_codes

        cursor.execute(f"SELECT COUNT(DISTINCT {stock_column}) FROM {table_name}{stock_filter}", params)
        actual_count = cursor.fetchone()[0] or 0

        result = []
        for period in periods:
            expected_count = expected_counts.get(period, 0)
            if expected_count <= 0:
                result.append(-1)
            else:
                result.append(min(1.0, round(actual_count / expected_count, 2)))

        return result

    def _load_non_stock_counts_by_period(self, cursor, table_name, date_column, periods, frequency):
        """一次性加载非股票级别数据的各周期计数"""
        cache_key = f"{table_name}_{date_column}_{frequency}"
        if cache_key in self._non_stock_counts_cache:
            return self._non_stock_counts_cache[cache_key]

        start_date, end_date = self._get_period_range(periods[0], frequency)
        _, end_date = self._get_period_range(periods[-1], frequency)

        date_format = self._get_date_format(frequency)

        if frequency == 'yearly':
            query = f"""
                SELECT YEAR({date_column}) as period, COUNT(*) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s
                GROUP BY YEAR({date_column})
            """
            cursor.execute(query, [start_date, end_date])
            result = {str(row[0]): row[1] for row in cursor.fetchall()}
        elif frequency == 'quarterly':
            query = f"""
                SELECT CONCAT(YEAR({date_column}), '-Q', QUARTER({date_column})) as period, COUNT(*) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s
                GROUP BY CONCAT(YEAR({date_column}), '-Q', QUARTER({date_column}))
            """
            cursor.execute(query, [start_date, end_date])
            result = {row[0]: row[1] for row in cursor.fetchall()}
        else:
            query = f"""
                SELECT DATE_FORMAT({date_column}, %s) as period, COUNT(*) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s
                GROUP BY DATE_FORMAT({date_column}, %s)
            """
            cursor.execute(query, [date_format, start_date, end_date, date_format])
            result = {row[0]: row[1] for row in cursor.fetchall()}

        self._non_stock_counts_cache[cache_key] = result
        return result

    def _calculate_non_stock_completeness(self, cursor, table_name, date_column, periods, frequency):
        """计算非股票级别数据的完整度（如行业信息、交易日）"""
        counts_by_period = self._load_non_stock_counts_by_period(cursor, table_name, date_column, periods, frequency)

        result = []
        for period in periods:
            count = counts_by_period.get(period, 0)
            result.append(1.0 if count > 0 else 0.0)

        return result

    def _calculate_point_completeness(self, cursor, table_name, date_column, periods, frequency, stock_column='symbol'):
        """计算非周期性数据的完整度"""
        if self.index_code:
            expected_counts = self._get_expected_stock_counts(cursor, periods, frequency)
            start_date, end_date = self._get_period_range(periods[0], frequency)
            _, end_date = self._get_period_range(periods[-1], frequency)
            index_constituents_by_period = self._load_index_constituents_by_period(
                cursor, periods, frequency, start_date, end_date
            )
            result = []
            for period in periods:
                constituents = index_constituents_by_period.get(period, set())
                expected_count = expected_counts.get(period, 0)
                if expected_count <= 0 or not constituents:
                    result.append(-1)
                    continue
                placeholders = ','.join(['%s'] * len(constituents))
                cursor.execute(
                    f"SELECT COUNT(DISTINCT {stock_column}) FROM {table_name} WHERE {stock_column} IN ({placeholders})",
                    sorted(constituents),
                )
                actual_count = cursor.fetchone()[0] or 0
                result.append(round(actual_count / expected_count, 2))
            return result

        cursor.execute(f"SELECT COUNT(DISTINCT {stock_column}) FROM {table_name}")
        actual_count = cursor.fetchone()[0] or 0

        expected_counts = self._get_expected_stock_counts(cursor, periods, frequency)
        latest_period = periods[-1] if periods else None
        expected_count = expected_counts.get(latest_period, 1)

        ratio = round(actual_count / expected_count, 2) if expected_count > 0 else 0.0
        return [ratio] * len(periods)

    def _calculate_event_security_completeness(self, cursor, table_name, date_column, periods, frequency, stock_column='symbol'):
        """计算事件型证券数据完整度；无事件期不等同于缺失。"""
        if not periods:
            return []

        start_date, end_date = self._get_period_range(periods[0], frequency)
        _, end_date = self._get_period_range(periods[-1], frequency)

        if self.index_code:
            index_constituents_by_period = self._load_index_constituents_by_period(
                cursor, periods, frequency, start_date, end_date
            )
            period_specs = self._build_index_period_specs(cursor, periods, frequency, start_date, end_date)
            counts_by_period = self._load_index_period_counts_python(
                cursor,
                table_name,
                date_column,
                stock_column,
                period_specs,
                index_constituents_by_period,
                frequency,
            )
            return [
                1.0 if counts_by_period.get(period, 0) > 0 else -1
                if index_constituents_by_period.get(period, set()) else -1
                for period in periods
            ]

        stock_filter = ""
        params = []
        if self.stock_codes:
            placeholders = ','.join(['%s'] * len(self.stock_codes))
            stock_filter = f" AND {stock_column} IN ({placeholders})"
            params = self.stock_codes

        if frequency == 'yearly':
            query = f"""
                SELECT YEAR({date_column}) as period, COUNT(*) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s{stock_filter}
                GROUP BY YEAR({date_column})
            """
            cursor.execute(query, [start_date, end_date] + params)
            counts_by_period = {str(row[0]): row[1] for row in cursor.fetchall()}
        elif frequency == 'quarterly':
            query = f"""
                SELECT CONCAT(YEAR({date_column}), '-Q', QUARTER({date_column})) as period, COUNT(*) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s{stock_filter}
                GROUP BY CONCAT(YEAR({date_column}), '-Q', QUARTER({date_column}))
            """
            cursor.execute(query, [start_date, end_date] + params)
            counts_by_period = {row[0]: row[1] for row in cursor.fetchall()}
        else:
            date_format = self._get_date_format(frequency)
            query = f"""
                SELECT DATE_FORMAT({date_column}, %s) as period, COUNT(*) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s{stock_filter}
                GROUP BY DATE_FORMAT({date_column}, %s)
            """
            cursor.execute(query, [date_format, start_date, end_date] + params + [date_format])
            counts_by_period = {row[0]: row[1] for row in cursor.fetchall()}

        return [
            1.0 if counts_by_period.get(period, 0) > 0 else -1
            for period in periods
        ]

    def _calculate_trading_day_security_completeness(self, cursor, config, periods, frequency):
        """计算交易日证券状态完整度。"""
        if not periods:
            return []

        table_name = config['table']
        date_column = config['date_column']
        stock_column = config.get('stock_column', 'symbol')

        start_date, end_date = self._get_period_range(periods[0], frequency)
        _, end_date = self._get_period_range(periods[-1], frequency)

        anchor_trade_days = self._get_period_anchor_trade_days(cursor, periods, frequency, start_date, end_date)
        if not anchor_trade_days:
            return [-1] * len(periods)

        period_date_values = [
            (period, anchor_trade_days[period])
            for period in periods
            if period in anchor_trade_days
        ]

        if self.index_code:
            index_constituents_by_period = self._load_index_constituents_by_period(
                cursor, periods, frequency, start_date, end_date
            )
            expected_by_period = {
                period: len(index_constituents_by_period.get(period, set()))
                for period in periods
            }
        else:
            index_constituents_by_period = None
            expected_by_period = self._load_trading_day_security_expected_counts(
                cursor, periods, frequency, start_date, end_date
            )

        actual_by_period = {}
        if period_date_values:
            if index_constituents_by_period is not None:
                period_specs = self._build_index_period_specs(cursor, periods, frequency, start_date, end_date)
                actual_by_period = self._load_index_anchor_date_counts_python(
                    cursor,
                    table_name,
                    date_column,
                    stock_column,
                    period_specs,
                    index_constituents_by_period,
                )
            else:
                actual_by_period = self._load_anchor_security_counts_python(
                    cursor,
                    table_name,
                    date_column,
                    stock_column,
                    period_date_values,
                    start_date,
                    end_date,
                )

        result = []
        for period in periods:
            expected_count = expected_by_period.get(period, 0)
            if expected_count <= 0:
                result.append(-1)
            else:
                actual_count = actual_by_period.get(period, 0)
                result.append(round(actual_count / expected_count, 2))

        return result

    def _get_period_anchor_trade_days(self, cursor, periods, frequency, start_date, end_date):
        """返回每个展示周期最后一个交易日。"""
        cache_key = (frequency, tuple(periods), str(start_date), str(end_date))
        if cache_key in self._period_anchor_trade_days_cache:
            return self._period_anchor_trade_days_cache[cache_key]

        trade_days = self._load_trade_days(cursor, start_date, end_date)
        period_set = set(periods)
        anchors = {}
        for trade_day in trade_days:
            period = self._get_period_label_for_date(trade_day, frequency)
            if period in period_set:
                anchors[period] = trade_day

        self._period_anchor_trade_days_cache[cache_key] = anchors
        return anchors

    def _load_index_constituents_by_period(self, cursor, periods, frequency, start_date, end_date):
        """按周期锚点交易日加载当时最新的指数成分股。"""
        if not self.index_code:
            return {}

        cache_key = (self.index_code, frequency, tuple(periods), str(start_date), str(end_date))
        if cache_key in self._index_constituents_cache:
            return self._index_constituents_cache[cache_key]

        anchor_trade_days = self._get_period_anchor_trade_days(cursor, periods, frequency, start_date, end_date)
        if not anchor_trade_days:
            self._index_constituents_cache[cache_key] = {}
            return {}

        constituents_by_date = resolve_index_constituents_by_dates(
            cursor,
            self.index_code,
            anchor_trade_days.values(),
        )
        result = {}
        for period, anchor_date in anchor_trade_days.items():
            result[period] = set(constituents_by_date.get(anchor_date, set()))

        self._index_constituents_cache[cache_key] = result
        return result

    def _build_index_period_specs(self, cursor, periods, frequency, start_date, end_date, aggregate_frequency=None):
        """Build period metadata for batched index-scope SQL."""
        if not self.index_code:
            return []

        cache_key = (
            self.index_code,
            frequency,
            tuple(periods),
            str(start_date),
            str(end_date),
            aggregate_frequency,
        )
        if cache_key in self._index_period_specs_cache:
            return self._index_period_specs_cache[cache_key]

        anchor_trade_days = self._get_period_anchor_trade_days(cursor, periods, frequency, start_date, end_date)
        if not anchor_trade_days:
            self._index_period_specs_cache[cache_key] = []
            return []

        payloads_by_anchor_date = resolve_index_constituent_payloads_by_dates(
            cursor,
            self.index_code,
            anchor_trade_days.values(),
        )
        specs = []
        for period in periods:
            anchor_date = anchor_trade_days.get(period)
            if not anchor_date:
                continue
            index_date, _ = payloads_by_anchor_date.get(anchor_date, (None, set()))
            if not index_date:
                continue
            if index_date > anchor_date:
                continue
            if aggregate_frequency:
                period_start, period_end = self._get_aggregate_date_range(
                    self._get_aggregate_key(period, aggregate_frequency),
                    aggregate_frequency,
                )
            else:
                period_start, period_end = self._get_period_range(period, frequency)
            period_start = self._coerce_date(period_start)
            period_end = self._coerce_date(period_end)
            specs.append((period, period_start, period_end, anchor_date, index_date))
        self._index_period_specs_cache[cache_key] = specs
        return specs

    def _period_specs_values_sql(self, period_specs, include_range=True, include_anchor=False):
        """Return a derived-table SQL fragment and params for small period specs."""
        if not period_specs:
            return "", []

        selects = []
        params = []
        for period, period_start, period_end, anchor_date, index_date in period_specs:
            columns = ["%s AS period"]
            params.append(period)
            if include_range:
                columns.extend(["%s AS period_start", "%s AS period_end"])
                params.extend([period_start, period_end])
            if include_anchor:
                columns.append("%s AS anchor_date")
                params.append(anchor_date)
            columns.append("%s AS index_date")
            params.append(index_date)
            selects.append("SELECT " + ", ".join(columns))

        return " UNION ALL ".join(selects), params

    def _load_index_period_counts_python(
        self,
        cursor,
        table_name,
        date_column,
        stock_column,
        period_specs,
        index_constituents_by_period,
        frequency,
        aggregate_frequency=None,
    ):
        """Count index-scoped rows in Python to avoid slow large derived-table joins."""
        if not period_specs:
            return {}

        if table_name == 'saa_index_weights':
            return {
                period: len(index_constituents_by_period.get(period, set()))
                if self._coerce_date(period_start) <= self._coerce_date(index_date) <= self._coerce_date(period_end)
                else 0
                for period, period_start, period_end, _, index_date in period_specs
            }

        period_by_label = {period: period for period, *_ in period_specs}
        period_codes = {
            period: set()
            for period in period_by_label
            if index_constituents_by_period.get(period, set())
        }
        if not period_codes:
            return {}

        union_codes = sorted(set().union(*(index_constituents_by_period[period] for period in period_codes)))
        if not union_codes:
            return {}

        min_date = min(period_start for _, period_start, _, _, _ in period_specs)
        max_date = max(period_end for _, _, period_end, _, _ in period_specs)
        placeholders = ','.join(['%s'] * len(union_codes))
        cursor.execute(
            f"""
                SELECT DISTINCT {stock_column}, {date_column}
                FROM {table_name}
                WHERE {date_column} >= %s
                  AND {date_column} <= %s
                  AND {stock_column} IN ({placeholders})
            """,
            [min_date, max_date] + union_codes,
        )
        if aggregate_frequency:
            codes_by_aggregate = {}
            for code, value_date in cursor.fetchall():
                value_date = self._coerce_date(value_date)
                aggregate_key = self._get_aggregate_key(
                    self._get_period_label_for_date(value_date, frequency),
                    aggregate_frequency,
                )
                codes_by_aggregate.setdefault(aggregate_key, set()).add(code)

            return {
                period: len(codes_by_aggregate.get(self._get_aggregate_key(period, aggregate_frequency), set()).intersection(
                    index_constituents_by_period.get(period, set())
                ))
                for period in period_codes
            }

        codes_by_period = {}
        for code, value_date in cursor.fetchall():
            period = self._get_period_label_for_date(self._coerce_date(value_date), frequency)
            if period in period_codes:
                codes_by_period.setdefault(period, set()).add(code)

        return {
            period: len(codes_by_period.get(period, set()).intersection(index_constituents_by_period.get(period, set())))
            for period in period_codes
        }

    def _load_index_anchor_date_counts_python(
        self,
        cursor,
        table_name,
        date_column,
        stock_column,
        period_specs,
        index_constituents_by_period,
    ):
        """Count index-scoped rows on each period anchor date."""
        if not period_specs:
            return {}

        periods_by_anchor = {}
        for period, _, _, anchor_date, _ in period_specs:
            if index_constituents_by_period.get(period, set()):
                periods_by_anchor.setdefault(anchor_date, []).append(period)
        if not periods_by_anchor:
            return {}

        union_codes = sorted(set().union(*(index_constituents_by_period[period] for periods in periods_by_anchor.values() for period in periods)))
        if not union_codes:
            return {}

        date_placeholders = ','.join(['%s'] * len(periods_by_anchor))
        code_placeholders = ','.join(['%s'] * len(union_codes))
        anchor_dates = sorted(periods_by_anchor)
        cursor.execute(
            f"""
                SELECT DISTINCT {stock_column}, {date_column}
                FROM {table_name}
                WHERE {date_column} IN ({date_placeholders})
                  AND {stock_column} IN ({code_placeholders})
            """,
            anchor_dates + union_codes,
        )

        codes_by_anchor = {}
        for code, value_date in cursor.fetchall():
            codes_by_anchor.setdefault(self._coerce_date(value_date), set()).add(code)

        counts = {}
        for anchor_date, anchor_periods in periods_by_anchor.items():
            actual_codes = codes_by_anchor.get(anchor_date, set())
            for period in anchor_periods:
                counts[period] = len(actual_codes.intersection(index_constituents_by_period.get(period, set())))
        return counts

    def _ratio_for_constituents(self, actual_codes, constituents, expected_count):
        if expected_count <= 0 or not constituents:
            return -1
        actual_count = len(actual_codes.intersection(constituents))
        return min(1.0, round(actual_count / expected_count, 2))

    def _load_trading_day_security_expected_counts(self, cursor, periods, frequency, start_date, end_date):
        """计算交易日证券状态的预期数量，避免数据库执行大区间 JOIN。"""
        anchor_trade_days = self._get_period_anchor_trade_days(cursor, periods, frequency, start_date, end_date)
        if not anchor_trade_days:
            return {}

        active_ranges = self._load_security_active_ranges(cursor, start_date, end_date)
        return self._count_active_securities_by_anchor(periods, anchor_trade_days, active_ranges)

    def _count_active_securities_by_anchor(self, periods, anchor_trade_days, active_ranges):
        starts = []
        ends = []
        for _, security_start, security_end in active_ranges:
            starts.append(security_start)
            ends.append(security_end)

        starts.sort()
        ends.sort()

        expected_by_period = {period: 0 for period in periods}
        active_count = 0
        start_index = 0
        end_index = 0

        for period, trade_day in sorted(anchor_trade_days.items(), key=lambda item: item[1]):
            while start_index < len(starts) and starts[start_index] <= trade_day:
                active_count += 1
                start_index += 1
            while end_index < len(ends) and ends[end_index] < trade_day:
                active_count -= 1
                end_index += 1

            expected_by_period[period] = active_count

        return expected_by_period

    def _load_anchor_security_counts_python(
        self,
        cursor,
        table_name,
        date_column,
        stock_column,
        period_date_values,
        start_date,
        end_date,
    ):
        """统计锚点交易日实际数据，证券有效性使用预加载 universe 在内存判断。"""
        if not period_date_values:
            return {}

        anchor_dates = sorted({anchor_date for _, anchor_date in period_date_values})
        date_placeholders = ','.join(['%s'] * len(anchor_dates))
        stock_filter = ""
        params = list(anchor_dates)
        if self.stock_codes:
            placeholders = ','.join(['%s'] * len(self.stock_codes))
            stock_filter = f" AND {stock_column} IN ({placeholders})"
            params.extend(self.stock_codes)

        cursor.execute(
            f"""
                SELECT DISTINCT {stock_column}, {date_column}
                FROM {table_name}
                WHERE {date_column} IN ({date_placeholders}){stock_filter}
            """,
            params,
        )

        actual_codes_by_date = {}
        for code, value_date in cursor.fetchall():
            actual_codes_by_date.setdefault(self._coerce_date(value_date), set()).add(code)

        active_codes_by_date = {anchor_date: set() for anchor_date in anchor_dates}
        for code, security_start, security_end in self._load_security_active_ranges(cursor, start_date, end_date):
            for anchor_date in anchor_dates:
                if security_start <= anchor_date <= security_end:
                    active_codes_by_date[anchor_date].add(code)

        return {
            period: len(
                actual_codes_by_date.get(anchor_date, set()).intersection(
                    active_codes_by_date.get(anchor_date, set())
                )
            )
            for period, anchor_date in period_date_values
        }

    def _coerce_date(self, value, default=None):
        if value is None:
            return default
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if hasattr(value, 'date'):
            return value.date()
        return date.fromisoformat(str(value)[:10])

    def _get_period_label_for_date(self, value, frequency):
        return get_period_label_for_date(value, frequency)

    def _calculate_completeness(self, cursor, table_name, date_column, periods, frequency, data_frequency, stock_column='symbol'):
        """计算完整度（支持聚合）"""
        if not periods:
            return []

        need_aggregation = (
            (data_frequency == 'yearly' and frequency in ('quarterly', 'monthly')) or
            (data_frequency == 'quarterly' and frequency == 'monthly')
        )

        if need_aggregation:
            return self._calculate_completeness_aggregated(cursor, table_name, date_column, periods, frequency, data_frequency, stock_column)

        expected_counts = self._get_expected_stock_counts(cursor, periods, frequency)

        result = []
        for period in periods:
            if not self._is_period_applicable(period, frequency, data_frequency):
                result.append(-1)
            else:
                result.append(None)

        applicable_indices = [i for i, v in enumerate(result) if v is None]
        if not applicable_indices:
            return result

        applicable_periods = [periods[i] for i in applicable_indices]
        start_date, end_date = self._get_period_range(applicable_periods[0], frequency)
        _, end_date = self._get_period_range(applicable_periods[-1], frequency)

        if self.index_code and table_name != 'saa_trade_days':
            index_constituents_by_period = self._load_index_constituents_by_period(
                cursor, periods, frequency, start_date, end_date
            )
            period_specs = self._build_index_period_specs(cursor, applicable_periods, frequency, start_date, end_date)
            period_counts = self._load_index_period_counts_python(
                cursor,
                table_name,
                date_column,
                stock_column,
                period_specs,
                index_constituents_by_period,
                frequency,
            )
            for i in applicable_indices:
                period = periods[i]
                constituents = index_constituents_by_period.get(period, set())
                expected_count = expected_counts.get(period, 0)
                if expected_count <= 0 or not constituents:
                    result[i] = -1
                    continue
                actual_count = period_counts.get(period, 0)
                result[i] = round(actual_count / expected_count, 2)
            return result

        date_format = self._get_date_format(frequency)

        stock_filter = ""
        params = []
        if self.stock_codes:
            placeholders = ','.join(['%s'] * len(self.stock_codes))
            stock_filter = f" AND {stock_column} IN ({placeholders})"
            params = self.stock_codes

        if data_frequency == 'yearly':
            query = f"""
                SELECT YEAR({date_column}) as year, COUNT(DISTINCT {stock_column}) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s{stock_filter}
                GROUP BY YEAR({date_column})
            """
            params = [start_date, end_date] + params
            cursor.execute(query, params)
            period_counts = {str(row[0]): row[1] for row in cursor.fetchall()}
        else:
            query = f"""
                SELECT DATE_FORMAT({date_column}, '%Y-%m') as month, COUNT(DISTINCT {stock_column}) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s{stock_filter}
                GROUP BY DATE_FORMAT({date_column}, '%Y-%m')
            """
            params = [start_date, end_date] + params
            cursor.execute(query, params)
            period_counts = {self._get_period_key(row[0], frequency): row[1] for row in cursor.fetchall()}

        for i in applicable_indices:
            period = periods[i]
            period_key = self._get_period_key(period, frequency)
            actual_count = period_counts.get(period_key, 0)
            if table_name == 'saa_trade_days':
                expected = self._get_expected_trade_days(period, frequency)
                result[i] = round(actual_count / expected, 2) if expected > 0 else 0.0
            else:
                expected_count = expected_counts.get(period, 1)
                result[i] = round(actual_count / expected_count, 2) if expected_count > 0 else 0.0

        return result

    def _calculate_completeness_aggregated(self, cursor, table_name, date_column, periods, frequency, data_frequency, stock_column='symbol'):
        """聚合计算（季度数据在月度视图，或年度数据在季度/月度视图）"""
        expected_counts = self._get_expected_stock_counts(cursor, periods, frequency)

        aggregate_keys = {}
        for i, period in enumerate(periods):
            agg_key = self._get_aggregate_key(period, data_frequency)
            if agg_key not in aggregate_keys:
                aggregate_keys[agg_key] = []
            aggregate_keys[agg_key].append(i)

        start_date, end_date = self._get_period_range(periods[0], frequency)
        _, end_date = self._get_period_range(periods[-1], frequency)

        if self.index_code:
            index_constituents_by_period = self._load_index_constituents_by_period(
                cursor, periods, frequency, start_date, end_date
            )
            period_specs = self._build_index_period_specs(
                cursor,
                periods,
                frequency,
                start_date,
                end_date,
                aggregate_frequency=data_frequency,
            )
            period_counts = self._load_index_period_counts_python(
                cursor,
                table_name,
                date_column,
                stock_column,
                period_specs,
                index_constituents_by_period,
                frequency,
                aggregate_frequency=data_frequency,
            )
            result = [0.0] * len(periods)
            for agg_key, indices in aggregate_keys.items():
                for i in indices:
                    period = periods[i]
                    if not self._is_period_applicable(period, frequency, data_frequency):
                        result[i] = -1
                        continue
                    constituents = index_constituents_by_period.get(period, set())
                    expected_count = expected_counts.get(period, 0)
                    if expected_count <= 0 or not constituents:
                        result[i] = -1
                        continue
                    actual_count = period_counts.get(period, 0)
                    result[i] = round(actual_count / expected_count, 2)
            return result

        stock_filter = ""
        params = []
        if self.stock_codes:
            placeholders = ','.join(['%s'] * len(self.stock_codes))
            stock_filter = f" AND {stock_column} IN ({placeholders})"
            params = self.stock_codes


        if data_frequency == 'yearly':
            query = f"""
                SELECT YEAR({date_column}) as year, COUNT(DISTINCT {stock_column}) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s{stock_filter}
                GROUP BY YEAR({date_column})
            """
            params = [start_date, end_date] + params
            cursor.execute(query, params)
            raw_counts = {str(row[0]): row[1] for row in cursor.fetchall()}
        elif data_frequency == 'quarterly':
            query = f"""
                SELECT
                    CONCAT(YEAR({date_column}), '-Q', QUARTER({date_column})) as quarter_key,
                    COUNT(DISTINCT {stock_column}) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s{stock_filter}
                GROUP BY CONCAT(YEAR({date_column}), '-Q', QUARTER({date_column}))
            """
            params = [start_date, end_date] + params
            cursor.execute(query, params)
            raw_counts = {row[0]: row[1] for row in cursor.fetchall()}
        else:
            query = f"""
                SELECT DATE_FORMAT({date_column}, '%Y-%m') as month, COUNT(DISTINCT {stock_column}) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s{stock_filter}
                GROUP BY DATE_FORMAT({date_column}, '%Y-%m')
            """
            params = [start_date, end_date] + params
            cursor.execute(query, params)
            raw_counts = {str(row[0]): row[1] for row in cursor.fetchall()}

        result = [0.0] * len(periods)
        for agg_key, indices in aggregate_keys.items():
            actual_count = raw_counts.get(agg_key, 0)
            for i in indices:
                period = periods[i]
                if not self._is_period_applicable(period, frequency, data_frequency):
                    result[i] = -1
                else:
                    expected_count = expected_counts.get(period, 1)
                    result[i] = round(actual_count / expected_count, 2) if expected_count > 0 else 0.0

        return result

    def _is_period_applicable(self, period, frequency, data_frequency):
        """判断 period 是否适用于该数据频率"""
        if data_frequency is None or data_frequency == 'daily':
            return True

        if data_frequency == 'quarterly':
            if frequency == 'daily':
                return False
            if frequency == 'monthly':
                month = int(period[5:7])
                return month in (3, 6, 9, 12)
            return True

        if data_frequency == 'monthly':
            return frequency != 'daily'

        if data_frequency == 'yearly':
            return True

        return True

    def _get_aggregate_key(self, period, data_frequency):
        """获取聚合键"""
        if data_frequency == 'yearly':
            return period[:4]
        elif data_frequency == 'quarterly':
            year = period[:4]
            month = int(period[5:7])
            quarter = (month - 1) // 3 + 1
            return f"{year}-Q{quarter}"
        return period

    def _get_aggregate_date_range(self, aggregate_key, data_frequency):
        if data_frequency == 'yearly':
            year = int(aggregate_key)
            return date(year, 1, 1), date(year, 12, 31)
        if data_frequency == 'quarterly':
            year = int(aggregate_key[:4])
            quarter = int(aggregate_key[6])
            start_month = (quarter - 1) * 3 + 1
            end_month = quarter * 3
            _, end_day = monthrange(year, end_month)
            return date(year, start_month, 1), date(year, end_month, end_day)
        year, month = int(aggregate_key[:4]), int(aggregate_key[5:7])
        _, end_day = monthrange(year, month)
        return date(year, month, 1), date(year, month, end_day)

    def _get_period_key(self, period, frequency):
        """获取周期键"""
        if frequency == 'quarterly':
            if '-Q' in period:
                year = period[:4]
                quarter = int(period[6])
                end_month = quarter * 3
                return f"{year}-{end_month:02d}"
            return period
        return period

    def _get_date_format(self, frequency):
        """获取日期格式"""
        formats = {
            'daily': '%Y-%m-%d',
            'monthly': '%Y-%m',
            'quarterly': '%Y-%m',
            'yearly': '%Y',
        }
        return formats.get(frequency, '%Y-%m')

    def _get_period_sql_expression(self, column, frequency):
        """获取 MySQL 周期表达式。"""
        if frequency == 'yearly':
            return f"YEAR({column})"
        if frequency == 'quarterly':
            return f"CONCAT(YEAR({column}), '-Q', QUARTER({column}))"
        return f"DATE_FORMAT({column}, %s)"

    def _get_period_range(self, period, frequency):
        """获取周期的日期范围"""
        return get_period_range(period, frequency)

    def _get_expected_trade_days(self, period, frequency):
        """获取预期交易日数（天数 - 最小周末数）"""
        if frequency == 'monthly':
            year, month = int(period[:4]), int(period[5:7])
            _, days_in_month = monthrange(year, month)
            return days_in_month - 8
        elif frequency == 'quarterly':
            year = int(period[:4])
            quarter = int(period[6])
            start_month = (quarter - 1) * 3 + 1
            total_days = sum(monthrange(year, m)[1] for m in range(start_month, start_month + 3))
            return total_days - 12
        elif frequency == 'yearly':
            year = int(period)
            days = 366 if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0) else 365
            return days - 104
        return 20
