"""
数据完整度计算模块

提供统一的完整度计算逻辑，供仪表盘热力图和完整度报告热力图使用。
"""
from datetime import date, datetime, timedelta
from django.db import connection

from .constants import DATA_TYPE_CONFIG, EARLIEST_YEAR


class CompletenessCalculator:
    """数据完整度计算器"""

    DATA_TYPE_CONFIG = DATA_TYPE_CONFIG
    
    def __init__(self, frequency: str, stock_codes: list = None, date_end: date = None):
        """
        初始化计算器
        
        Args:
            frequency: 显示频率 (daily/weekly/monthly/quarterly/yearly)
            stock_codes: 股票范围，None 表示全部股票
            date_end: 截止日期，用于筛选上市股票
        """
        self.frequency = frequency
        self.stock_codes = stock_codes
        self.date_end = date_end or date.today()
        self._listing_dates = None
        self._stocks_by_period = {}
    
    def calculate(self, data_type: str, periods: list, start_date: date = None, end_date: date = None) -> list:
        """
        计算指定数据类型的完整度
        
        Args:
            data_type: 数据类型
            periods: 周期列表
            start_date: 数据开始日期
            end_date: 数据结束日期
            
        Returns:
            完整度列表，-1 表示不适用，0-1 表示完整度
        """
        config = self.DATA_TYPE_CONFIG.get(data_type)
        if not config:
            return [-1] * len(periods)
        
        if data_type == 'trade_days':
            return self._calculate_trade_days_completeness(periods, start_date, end_date)
        
        if data_type == 'stock_info':
            return self._calculate_stock_info_completeness(periods)
        
        if data_type == 'quote':
            return self._calculate_quote_completeness(periods, end_date or self.date_end)
        
        return self._calculate_stock_level_completeness(
            config['table'], 
            config['date_column'],
            config['data_frequency'],
            periods,
            start_date,
            end_date,
            config.get('stock_column', 'symbol')
        )
    
    def calculate_all(self, data_types: list, periods: list, start_date: date = None, end_date: date = None) -> dict:
        """
        批量计算多个数据类型的完整度
        
        Returns:
            {
                'periods': [...],
                'matrix': {data_type: [values...]}
            }
        """
        matrix = {}
        for data_type in data_types:
            matrix[data_type] = self.calculate(data_type, periods, start_date, end_date)
        
        return {
            'periods': periods,
            'matrix': matrix,
        }
    
    def _calculate_trade_days_completeness(self, periods: list, start_date: date, end_date: date) -> list:
        """计算交易日完整度"""
        if not start_date or not end_date:
            return [-1] * len(periods)
        
        existing_periods = self._get_trade_days_periods(start_date, end_date)
        
        result = []
        for period in periods:
            if period in existing_periods:
                result.append(1.0)
            else:
                result.append(-1)
        
        return result
    
    def _calculate_stock_info_completeness(self, periods: list) -> list:
        """计算股票基本信息完整度"""
        with connection.cursor() as cursor:
            if self.stock_codes:
                cursor.execute("""
                    SELECT COUNT(*) FROM saa_stocks
                    WHERE symbol IN %s
                """, [self.stock_codes])
            else:
                cursor.execute("SELECT COUNT(*) FROM saa_stocks")
            
            count = cursor.fetchone()[0] or 0
        
        value = 1.0 if count > 0 else -1
        return [value] * len(periods)
    
    def _calculate_quote_completeness(self, periods: list, date_end: date) -> list:
        """计算最新行情完整度（非周期性数据）"""
        latest_date = self._get_latest_trade_date(date_end)
        if not latest_date:
            return [-1] * len(periods)
        
        latest_period = self._convert_date_to_period(latest_date, self.frequency)
        
        total_stocks = self._get_total_stocks()
        
        with connection.cursor() as cursor:
            if self.stock_codes:
                cursor.execute("""
                    SELECT COUNT(DISTINCT symbol) FROM saa_latest_prices
                    WHERE symbol IN %s
                """, [self.stock_codes])
            else:
                cursor.execute("SELECT COUNT(DISTINCT symbol) FROM saa_latest_prices")
            
            data_count = cursor.fetchone()[0] or 0
        
        if total_stocks > 0:
            completeness = round(data_count / total_stocks, 2)
            completeness = min(1.0, max(0.0, completeness))
        else:
            completeness = -1
        
        result = []
        for period in periods:
            if period == latest_period:
                result.append(completeness)
            else:
                result.append(-1)
        
        return result
    
    def _calculate_stock_level_completeness(
        self, 
        table: str, 
        date_column: str,
        data_frequency: str,
        periods: list,
        start_date: date,
        end_date: date,
        stock_column: str = 'symbol'
    ) -> list:
        """计算股票级别周期性数据的完整度"""
        if not start_date or not end_date:
            return [-1] * len(periods)
        
        stocks_by_period = self._get_stocks_count_by_period(periods)
        
        data_by_period = self._get_data_count_by_period(
            table, date_column, data_frequency, periods, start_date, end_date, stock_column
        )
        
        result = []
        for period in periods:
            denominator = stocks_by_period.get(period, 0)
            numerator = data_by_period.get(period, 0)
            
            if denominator == 0:
                result.append(-1)
            elif numerator == 0:
                result.append(-1)
            else:
                completeness = round(numerator / denominator, 2)
                result.append(min(1.0, max(0.0, completeness)))
        
        return result
    
    def _get_listing_dates(self) -> list:
        """获取股票上市日期列表"""
        if self._listing_dates is not None:
            return self._listing_dates
        
        with connection.cursor() as cursor:
            if self.stock_codes:
                cursor.execute("""
                    SELECT listing_time FROM saa_stocks
                    WHERE symbol IN %s AND listing_time IS NOT NULL
                """, [self.stock_codes])
            else:
                cursor.execute("""
                    SELECT listing_time FROM saa_stocks
                    WHERE listing_time IS NOT NULL
                """)
            
            self._listing_dates = [row[0] for row in cursor.fetchall() if row[0]]
        
        return self._listing_dates
    
    def _get_stocks_count_by_period(self, periods: list) -> dict:
        """计算每个 period 应有的股票数（分母）"""
        listing_dates = self._get_listing_dates()
        
        result = {}
        for period in periods:
            period_start = self._get_period_start_date(period)
            if period_start:
                count = sum(1 for d in listing_dates if d and d <= period_start)
            else:
                count = 0
            result[period] = count
        
        return result
    
    def _get_data_count_by_period(
        self,
        table: str,
        date_column: str,
        data_frequency: str,
        periods: list,
        start_date: date,
        end_date: date,
        stock_column: str = 'symbol'
    ) -> dict:
        """计算每个 period 有数据的股票数（分子）"""
        date_format = self._get_date_format(self.frequency)
        
        stock_filter = ""
        params = []
        
        if self.stock_codes:
            stock_filter = f"AND {stock_column} IN %s"
            params = [self.stock_codes]
        
        query = f"""
            SELECT DATE_FORMAT({date_column}, %s) as period, COUNT(DISTINCT {stock_column}) as cnt
            FROM {table}
            WHERE {date_column} >= %s AND {date_column} <= %s
            {stock_filter}
            GROUP BY DATE_FORMAT({date_column}, %s)
        """
        
        params = [date_format, start_date, end_date] + params + [date_format]
        
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            result = {}
            for row in cursor.fetchall():
                period_key = self._normalize_period(row[0])
                result[period_key] = row[1]
        
        return result
    
    def _get_trade_days_periods(self, start_date: date, end_date: date) -> set:
        """获取交易日实际存在的 periods"""
        date_format = self._get_date_format(self.frequency)
        
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT DISTINCT DATE_FORMAT(date, %s) as period
                FROM saa_trade_days
                WHERE date BETWEEN %s AND %s
            """, [date_format, start_date, end_date])
            
            return {self._normalize_period(row[0]) for row in cursor.fetchall()}
    
    def _get_latest_trade_date(self, max_date: date) -> date:
        """获取小于等于指定日期的最新交易日"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT MAX(date) FROM saa_trade_days
                WHERE date <= %s
            """, [max_date])
            result = cursor.fetchone()[0]
            return result
    
    def _get_total_stocks(self) -> int:
        """获取总股票数"""
        with connection.cursor() as cursor:
            if self.stock_codes:
                cursor.execute("""
                    SELECT COUNT(*) FROM saa_stocks
                    WHERE symbol IN %s AND listing_time IS NOT NULL
                """, [self.stock_codes])
            else:
                cursor.execute("""
                    SELECT COUNT(*) FROM saa_stocks
                    WHERE listing_time IS NOT NULL AND listing_time <= %s
                """, [self.date_end])
            
            return cursor.fetchone()[0] or 0
    
    def _get_period_start_date(self, period: str) -> date:
        """获取 period 的开始日期"""
        try:
            if self.frequency == 'yearly':
                return date(int(period), 1, 1)
            elif self.frequency == 'quarterly':
                year = int(period[:4])
                q = int(period[-1])
                return date(year, (q - 1) * 3 + 1, 1)
            elif self.frequency == 'monthly':
                return date(int(period[:4]), int(period[5:7]), 1)
            elif self.frequency == 'weekly':
                year = int(period[:4])
                week = int(period[6:8])
                dt = datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w")
                return dt.date()
            elif self.frequency == 'daily':
                return datetime.strptime(period, '%Y-%m-%d').date()
        except (ValueError, IndexError):
            pass
        return None
    
    def _convert_date_to_period(self, d: date, frequency: str) -> str:
        """将日期转换为 period 字符串"""
        if frequency == 'yearly':
            return str(d.year)
        elif frequency == 'quarterly':
            quarter = (d.month - 1) // 3 + 1
            return f"{d.year}-Q{quarter}"
        elif frequency == 'monthly':
            return f"{d.year}-{d.month:02d}"
        elif frequency == 'weekly':
            week = d.isocalendar()[1]
            return f"{d.year}-W{week:02d}"
        else:
            return str(d)
    
    def _get_date_format(self, frequency: str) -> str:
        """获取日期格式化字符串"""
        if frequency == 'yearly':
            return '%Y'
        elif frequency == 'quarterly':
            return '%Y-%m'
        elif frequency == 'monthly':
            return '%Y-%m'
        elif frequency == 'weekly':
            return '%Y-%m-%d'
        else:
            return '%Y-%m-%d'
    
    def _normalize_period(self, period_str: str) -> str:
        """标准化 period 字符串"""
        if not period_str:
            return period_str
        
        if self.frequency == 'quarterly':
            try:
                parts = period_str.split('-')
                if len(parts) == 2:
                    year = int(parts[0])
                    month = int(parts[1])
                    quarter = (month - 1) // 3 + 1
                    return f"{year}-Q{quarter}"
            except (ValueError, IndexError):
                pass
        
        return period_str
