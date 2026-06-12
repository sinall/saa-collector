# -*- coding: utf-8 -*-
import logging
from datetime import date as date_type, datetime

import mysql.connector
from django.utils import timezone

from saa_collector.services.common.config_service import ConfigService
from saa_collector.services.common.logging_utils import format_sample_record
from saa_collector.utils.db import DB


class StockStatusService:
    def __init__(self):
        self._logger = logging.getLogger()
        self.config_service = ConfigService()
        self.db_config = self.config_service.get_db_config()

    def collect(self, target_date=None, target_dates=None, symbols=None):
        cnx = mysql.connector.connect(**self.db_config)
        try:
            resolved_dates = self._resolve_target_dates(target_date, target_dates)
            if not resolved_dates:
                return

            stock_rows = self.load_stock_rows(cnx, symbols)
            for current_date in resolved_dates:
                records = self.build_records(stock_rows, current_date)
                self.save_records(records, cnx)
                self._logger.info(
                    'Saved %s records to saa_extras for date %s; sample=%s',
                    len(records),
                    current_date,
                    format_sample_record(records),
                )
        finally:
            cnx.close()

    def query_records(self, target_date, cnx, symbols=None):
        if not isinstance(target_date, date_type):
            raise TypeError('target_date must be a date')

        stock_rows = self.load_stock_rows(cnx, symbols)
        return self.build_records(stock_rows, target_date)

    def load_stock_rows(self, cnx, symbols=None):
        cursor = cnx.cursor()
        try:
            params = []
            symbol_clause = ''
            if symbols is not None:
                unique_symbols = sorted({symbol for symbol in symbols if symbol})
                if not unique_symbols:
                    return []
                placeholders = ','.join(['%s'] * len(unique_symbols))
                symbol_clause = f' AND symbol IN ({placeholders})'
                params.extend(unique_symbols)
            cursor.execute(
                f"""
                SELECT symbol, name
                FROM saa_stocks
                WHERE type = 'STOCK'
                  AND market = 'A'
                  AND symbol IS NOT NULL
                  {symbol_clause}
                ORDER BY symbol
                """,
                params,
            )
            return cursor.fetchall()
        finally:
            cursor.close()

    def build_records(self, stock_rows, target_date):
        return [
                {
                    'code': symbol,
                    'date': target_date,
                    'is_st': 1 if self.is_st_name(name) else 0,
                }
                for symbol, name in stock_rows
                if symbol
            ]

    def _resolve_target_dates(self, target_date=None, target_dates=None):
        if target_dates is not None:
            return [self._coerce_date(value) for value in target_dates if value]

        if target_date is None:
            target_date = timezone.localdate()

        if isinstance(target_date, (list, tuple, set)):
            return [self._coerce_date(value) for value in target_date if value]

        resolved = self._coerce_date(target_date)
        return [resolved] if resolved else []

    @staticmethod
    def _coerce_date(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date_type):
            return value
        return datetime.strptime(str(value), '%Y-%m-%d').date()

    def save_records(self, records, cnx):
        DB().to_sql(records, cnx, 'saa_extras', ['code', 'date'])

    @staticmethod
    def is_st_name(name):
        if not name:
            return False
        normalized = str(name).upper().replace('＊', '*').replace('Ｓ', 'S').replace('Ｔ', 'T')
        return 'ST' in normalized
