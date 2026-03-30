"""
完整度计算服务

提供统一的完整度计算逻辑，供仪表盘热力图和完整性报告热力图使用。
"""
from datetime import date, timedelta
from django.db import connection
from calendar import monthrange

from ..constants import DATA_TYPE_CONFIG, EARLIEST_YEAR


class CompletenessService:
    """完整度计算服务"""

    DATA_TYPE_CONFIG = [
        (key, config['label'], config['table'], config['date_column'], config['data_frequency'])
        for key, config in DATA_TYPE_CONFIG.items()
    ]

    def __init__(self, stock_codes=None, date_end=None):
        self.stock_codes = stock_codes
        self.date_end = date_end or date.today()
        self._stock_listing_times = None

    def _load_stock_listing_times(self, cursor):
        """
        一次性加载股票上市时间到内存
        
        Returns:
            list: [(listing_time or None), ...]
        """
        if self._stock_listing_times is not None:
            return self._stock_listing_times

        stock_filter = ""
        params = []
        if self.stock_codes:
            stock_filter = " WHERE symbol IN %s"
            params = [self.stock_codes]

        query = f"SELECT listing_time FROM saa_stocks{stock_filter}"
        cursor.execute(query, params)
        self._stock_listing_times = [row[0] for row in cursor.fetchall()]
        return self._stock_listing_times

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
        listing_times = self._load_stock_listing_times(cursor)

        result = {}
        for period in periods:
            period_end = self._get_period_end_date(period, frequency)
            count = sum(
                1 for listing_time in listing_times
                if listing_time is None or listing_time <= period_end
            )
            result[period] = max(count, 1)

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
            for key, label, table_name, date_column, data_frequency in data_type_configs:
                if date_column is None:
                    matrix[key] = [1.0] * len(periods)
                    continue
                
                if data_frequency is None:
                    matrix[key] = self._calculate_point_completeness(cursor, table_name, date_column, periods, frequency)
                    continue
                
                try:
                    matrix[key] = self._calculate_completeness(
                        cursor, table_name, date_column, periods, frequency, data_frequency
                    )
                except Exception as e:
                    matrix[key] = [0.0] * len(periods)
        
        start_date = periods[0] if periods else ''
        end_date = periods[-1] if periods else ''
        
        return {
            'date_range': {'start': start_date, 'end': end_date},
            'frequency': frequency,
            'periods': periods,
            'data_types': [
                {'key': key, 'label': label, 'frequency': data_freq}
                for key, label, _, _, data_freq in data_type_configs
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
        config_dict = {key: (key, label, table, date_col, data_freq) 
                       for key, label, table, date_col, data_freq in self.DATA_TYPE_CONFIG}
        
        if data_types:
            return [config_dict[dt] for dt in data_types if dt in config_dict]
        return self.DATA_TYPE_CONFIG
    
    def _calculate_point_completeness(self, cursor, table_name, date_column, periods, frequency):
        """计算非周期性数据的完整度"""
        cursor.execute(f"SELECT COUNT(DISTINCT symbol) FROM {table_name}")
        actual_count = cursor.fetchone()[0] or 0

        expected_counts = self._get_expected_stock_counts(cursor, periods, frequency)
        latest_period = periods[-1] if periods else None
        expected_count = expected_counts.get(latest_period, 1)

        ratio = round(actual_count / expected_count, 2) if expected_count > 0 else 0.0
        return [ratio] * len(periods)
    
    def _calculate_completeness(self, cursor, table_name, date_column, periods, frequency, data_frequency):
        """计算完整度（支持聚合）"""
        if not periods:
            return []

        need_aggregation = (
            (data_frequency == 'yearly' and frequency in ('quarterly', 'monthly')) or
            (data_frequency == 'quarterly' and frequency == 'monthly')
        )

        if need_aggregation:
            return self._calculate_completeness_aggregated(cursor, table_name, date_column, periods, frequency, data_frequency)

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

        date_format = self._get_date_format(frequency)

        stock_filter = ""
        params = []
        if self.stock_codes:
            stock_filter = " AND symbol IN %s"
            params = [self.stock_codes]

        query = f"""
            SELECT DATE_FORMAT({date_column}, %s) as period, COUNT(*) as cnt
            FROM {table_name}
            WHERE {date_column} >= %s AND {date_column} <= %s{stock_filter}
            GROUP BY DATE_FORMAT({date_column}, %s)
        """
        params = [date_format, start_date, end_date] + params + [date_format]

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
    
    def _calculate_completeness_aggregated(self, cursor, table_name, date_column, periods, frequency, data_frequency):
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

        stock_filter = ""
        params = []
        if self.stock_codes:
            stock_filter = " AND symbol IN %s"
            params = [self.stock_codes]

        if data_frequency == 'yearly':
            query = f"""
                SELECT YEAR({date_column}) as year, COUNT(*) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s{stock_filter}
                GROUP BY YEAR({date_column})
            """
            params = [start_date, end_date] + params
            cursor.execute(query, params)
            raw_counts = {str(row[0]): row[1] for row in cursor.fetchall()}
        else:
            query = f"""
                SELECT DATE_FORMAT({date_column}, '%Y-%m') as month, COUNT(*) as cnt
                FROM {table_name}
                WHERE {date_column} >= %s AND {date_column} <= %s{stock_filter}
                GROUP BY DATE_FORMAT({date_column}, '%Y-%m')
            """
            params = [start_date, end_date] + params
            cursor.execute(query, params)
            raw_counts = {}
            for row in cursor.fetchall():
                month_str = row[0]
                year = month_str[:4]
                month = int(month_str[5:7])
                quarter = (month - 1) // 3 + 1
                quarter_key = f"{year}-Q{quarter}"
                if quarter_key not in raw_counts:
                    raw_counts[quarter_key] = 0
                raw_counts[quarter_key] += row[1]

        result = [0.0] * len(periods)
        for agg_key, indices in aggregate_keys.items():
            actual_count = raw_counts.get(agg_key, 0)
            for i in indices:
                period = periods[i]
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
        
        if data_frequency == 'yearly':
            if frequency in ('daily', 'monthly'):
                return False
            if frequency == 'quarterly':
                quarter = int(period[6])
                return quarter == 4
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
    
    def _get_period_range(self, period, frequency):
        """获取周期的日期范围"""
        if frequency == 'daily':
            return period, period
        elif frequency == 'monthly':
            year, month = int(period[:4]), int(period[5:7])
            if month == 12:
                end = date(year, 12, 31)
            else:
                end = date(year, month + 1, 1) - timedelta(days=1)
            return f"{year}-{month:02d}-01", end.strftime('%Y-%m-%d')
        elif frequency == 'quarterly':
            year, quarter = int(period[:4]), int(period[6])
            start_month = (quarter - 1) * 3 + 1
            end_month = quarter * 3
            end_day = 31 if end_month in [3, 12] else 30 if end_month in [4, 6, 9, 11] else 28
            return f"{year}-{start_month:02d}-01", f"{year}-{end_month:02d}-{end_day}"
        elif frequency == 'yearly':
            year = int(period)
            return f"{year}-01-01", f"{year}-12-31"
        return period, period

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
