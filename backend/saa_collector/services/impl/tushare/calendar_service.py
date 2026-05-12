# -*- coding: utf-8 -*-
import logging
import time
from datetime import datetime, timedelta

import mysql.connector

from saa_collector.services.abstract.calendar_service import CalendarService
from saa_collector.services.common.config_service import ConfigService
from saa_collector.third_party.tushare_api_client import get_tushare_client


class CalendarServiceImpl(CalendarService):
    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()
        self.config_service = ConfigService()
        self.config = self.config_service.get_config()
        tushare_config = self.config.get('saa_collector', {}).get('tushare_api', {})
        token = tushare_config.get('token')
        rate_limit = tushare_config.get('rate_limit')
        self.pro = get_tushare_client(token, rate_limit=rate_limit)
        self.db_config = self.config_service.get_db_config()

    def collect(self, start_date, end_date):
        start_time = time.time()
        self._logger.info(f"Collecting trade days from {start_date} to {end_date}")

        df = self.pro.trade_cal(
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d'),
        )
        trade_dates = df[df['is_open'] == 1]['cal_date'].tolist()

        records = []
        for date_str in trade_dates:
            trade_date = datetime.strptime(str(date_str), '%Y%m%d').date()
            records.append({'date': trade_date})

        self._save_records(records)
        self._logger.info(f"Collected {len(records)} trade days in {int(time.time() - start_time)} seconds")

    def _save_records(self, records):
        if not records:
            self._logger.info("No trade days to save")
            return

        self._logger.info(f"Saving {len(records)} trade days to database")
        self._logger.info(f"Date range: {records[0]['date']} ~ {records[-1]['date']}")

        cnx = mysql.connector.connect(**self.db_config)
        cursor = cnx.cursor(prepared=True)

        sql = """
            INSERT INTO saa_trade_days (date) VALUES (%s)
            ON DUPLICATE KEY UPDATE date = VALUES(date)
        """

        for record in records:
            cursor.execute(sql, (record['date'],))

        cnx.commit()
        cursor.close()
        cnx.close()

        self._logger.info(f"Successfully saved {len(records)} trade days")

    def get_last_trade_day_monthly(self, exchange=None, start_date=None, end_date=None, is_open='1'):
        last_day_of_previous_month = self.get_last_day_of_previous_month()
        end_date = datetime.today()
        start_date = end_date - timedelta(days=45)
        df = self.pro.trade_cal(
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d'),
        )
        cal_dates = [datetime.strptime(str(d), '%Y%m%d') for d in df[df['is_open'] == 1]['cal_date'].tolist()]
        cal_dates = [d for d in cal_dates if d.date() <= last_day_of_previous_month.date()]
        last_trade_day = max(cal_dates)
        return last_trade_day

    def get_last_day_of_previous_month(self):
        today = datetime.today()
        first = today.replace(day=1)
        last_month = first - timedelta(days=1)
        return last_month
