# -*- coding: utf-8 -*-
import logging
from datetime import date as date_type

import mysql.connector
from django.utils import timezone

from saa_collector.services.common.config_service import ConfigService
from saa_collector.utils.db import DB


class StockStatusService:
    def __init__(self):
        self._logger = logging.getLogger()
        self.config_service = ConfigService()
        self.db_config = self.config_service.get_db_config()

    def collect(self, target_date=None):
        if target_date is None:
            target_date = timezone.localdate()
        cnx = mysql.connector.connect(**self.db_config)
        try:
            records = self.query_records(target_date, cnx)
            self.save_records(records, cnx)
            self._logger.info('Saved %s records to saa_extras for date %s', len(records), target_date)
        finally:
            cnx.close()

    def query_records(self, target_date, cnx):
        if not isinstance(target_date, date_type):
            raise TypeError('target_date must be a date')

        cursor = cnx.cursor()
        try:
            cursor.execute(
                """
                SELECT symbol, name
                FROM saa_stocks
                WHERE type = 'STOCK'
                  AND market = 'A'
                  AND symbol IS NOT NULL
                ORDER BY symbol
                """
            )
            return [
                {
                    'code': symbol,
                    'date': target_date,
                    'is_st': 1 if self.is_st_name(name) else 0,
                }
                for symbol, name in cursor.fetchall()
                if symbol
            ]
        finally:
            cursor.close()

    def save_records(self, records, cnx):
        DB().to_sql(records, cnx, 'saa_extras', ['code', 'date'])

    @staticmethod
    def is_st_name(name):
        if not name:
            return False
        normalized = str(name).upper().replace('＊', '*').replace('Ｓ', 'S').replace('Ｔ', 'T')
        return 'ST' in normalized
