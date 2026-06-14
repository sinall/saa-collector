# -*- coding: utf-8 -*-
import logging
from datetime import date as date_type
from datetime import datetime
from datetime import timedelta

import mysql.connector
import pandas as pd

from saa_collector.date_expressions import get_latest_trade_day_on_or_before
from saa_collector.services.common.config_service import ConfigService
from saa_collector.services.common.logging_utils import format_sample_record
from saa_collector.third_party.tushare_api_client import get_tushare_client
from saa_collector.utils.db import DB


class IndexWeightService:
    DEFAULT_INDEXES = ['000906']

    def __init__(self):
        self._logger = logging.getLogger()
        self.config_service = ConfigService()
        self.config = self.config_service.get_config()
        tushare_config = self.config.get('saa_collector').get('tushare_api')
        token = tushare_config['token']
        rate_limit = tushare_config.get('rate_limit')
        self.pro = get_tushare_client(token, rate_limit=rate_limit)
        self.db_config = self.config_service.get_db_config()

    def collect(self, indexes=None, start_date=None, end_date=None):
        indexes = self.build_indexes(indexes)
        start_date, end_date = self.normalize_date_range(start_date, end_date)
        date_ranges = self.generate_monthly_date_ranges(start_date, end_date)
        cnx = mysql.connector.connect(**self.db_config)
        try:
            records = []
            for index in indexes:
                for _, period_end in date_ranges:
                    trade_date = self.resolve_month_end_trade_date(period_end)
                    if trade_date is None:
                        continue
                    records.extend(self.query_records(index, trade_date, trade_date))
            stock_names = self.query_stock_names(cnx, [record['code'] for record in records])
            for record in records:
                record['display_name'] = stock_names.get(record['code'])
            self.save_records(records, cnx)
            self._logger.info(
                'Saved %s records to saa_index_weights; sample=%s',
                len(records),
                format_sample_record(records),
            )
        finally:
            cnx.close()

    def query_records(self, index, start_date, end_date):
        tushare_code = self.to_tushare_index_code(index)
        df = self.pro.query(
            'index_weight',
            index_code=tushare_code,
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d'),
        )
        if df.empty:
            return []
        return [
            self.transform_record(row)
            for row in df.to_dict('records')
        ]

    def query_stock_names(self, cnx, codes):
        codes = sorted(set(code for code in codes if code))
        if not codes:
            return {}

        placeholders = ','.join(['%s'] * len(codes))
        cursor = cnx.cursor()
        try:
            cursor.execute(
                'SELECT symbol, name FROM saa_stocks WHERE symbol IN ({})'.format(placeholders),
                codes,
            )
            return {
                symbol: name
                for symbol, name in cursor.fetchall()
            }
        finally:
            cursor.close()

    def save_records(self, records, cnx):
        DB().to_sql(records, cnx, 'saa_index_weights', ['index', 'date', 'code'])

    def transform_record(self, row):
        return {
            'index': self.strip_suffix(row.get('index_code')),
            'date': self.parse_tushare_date(row.get('trade_date')),
            'code': self.strip_suffix(row.get('con_code')),
            'display_name': None,
            'weight': self.nullable_value(row.get('weight')),
        }

    @classmethod
    def build_indexes(cls, indexes):
        if isinstance(indexes, str):
            indexes = [indexes]
        return sorted(indexes or cls.DEFAULT_INDEXES)

    @staticmethod
    def normalize_date_range(start_date, end_date):
        dates = [value for value in (start_date, end_date) if value is not None]
        if not dates:
            today = datetime.today().date()
            return today, today
        return min(dates), max(dates)

    @staticmethod
    def generate_monthly_date_ranges(start_date, end_date):
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime):
            end_date = end_date.date()
        if not isinstance(start_date, date_type) or not isinstance(end_date, date_type):
            return []
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        ranges = []
        year = start_date.year
        month = start_date.month
        while True:
            month_start = date_type(year, month, 1)
            if month == 12:
                next_month = date_type(year + 1, 1, 1)
            else:
                next_month = date_type(year, month + 1, 1)
            month_end = next_month - timedelta(days=1)
            period_start = max(start_date, month_start)
            period_end = min(end_date, month_end)
            if period_start <= period_end:
                ranges.append((period_start, period_end))
            if month_end >= end_date:
                break
            month += 1
            if month > 12:
                month = 1
                year += 1
        return ranges

    @staticmethod
    def resolve_month_end_trade_date(period_end):
        trade_date = get_latest_trade_day_on_or_before(period_end)
        return trade_date or period_end

    @staticmethod
    def to_tushare_index_code(index):
        if not index:
            return index
        if index.endswith('.XSHG'):
            return index.replace('.XSHG', '.SH')
        if index.endswith('.XSHE'):
            return index.replace('.XSHE', '.SZ')
        if str(index).isdigit() and len(str(index)) == 6:
            return '{}.SZ'.format(index) if str(index).startswith('399') else '{}.SH'.format(index)
        return index

    @staticmethod
    def to_joinquant_index_code(index):
        if not index:
            return index
        if index.endswith('.SH'):
            return index.replace('.SH', '.XSHG')
        if index.endswith('.SZ'):
            return index.replace('.SZ', '.XSHE')
        return index

    @staticmethod
    def strip_suffix(code):
        if not code:
            return code
        return str(code).split('.')[0]

    @staticmethod
    def parse_tushare_date(value):
        if isinstance(value, date_type):
            return value
        return datetime.strptime(str(value), '%Y%m%d').date()

    @staticmethod
    def nullable_value(value):
        if pd.isna(value):
            return None
        return value
