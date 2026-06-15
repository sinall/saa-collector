# -*- coding: utf-8 -*-
import logging
from datetime import date as date_type
from datetime import datetime

import mysql.connector
import pandas as pd

from saa_collector.services.common.config_service import ConfigService
from saa_collector.services.common.logging_utils import format_sample_record
from saa_collector.third_party.tushare_api_client import get_tushare_client
from saa_collector.utils.db import DB


class SwIndustryService:
    CATEGORY = 'sw_l1'

    def __init__(self):
        self._logger = logging.getLogger()
        self.config_service = ConfigService()
        self.config = self.config_service.get_config()
        tushare_config = self.config.get('saa_collector').get('tushare_api')
        token = tushare_config['token']
        rate_limit = tushare_config.get('rate_limit')
        self.pro = get_tushare_client(token, rate_limit=rate_limit)
        self.db_config = self.config_service.get_db_config()

    def collect_industries(self, target_date=None):
        target_date = self.normalize_target_date(target_date)
        cnx = mysql.connector.connect(**self.db_config)
        try:
            existing_start_dates = self.query_existing_start_dates(cnx)
            records = self.query_industry_records(target_date, existing_start_dates)
            self.save_industries(records, cnx)
            self._logger.info(
                'Saved %s records to saa_industries; sample=%s',
                len(records),
                format_sample_record(records),
            )
        finally:
            cnx.close()

    def collect_industry_stocks(self, industry_codes=None, target_date=None, target_dates=None):
        target_dates = self.normalize_target_dates(target_dates, target_date)
        cnx = mysql.connector.connect(**self.db_config)
        try:
            industry_codes = self.build_industry_codes(industry_codes, cnx)
            records = []
            for target_date in target_dates:
                for industry_code in industry_codes:
                    try:
                        records.extend(self.query_industry_stock_records(industry_code, target_date))
                    except (KeyError, ValueError) as exc:
                        self._logger.warning(
                            'Skipping SW industry constituents: industry_code=%s target_date=%s error=%s',
                            industry_code,
                            target_date,
                            exc,
                        )
            self.save_industry_stocks(records, cnx)
            self._logger.info(
                'Saved %s records to saa_industry_stocks; sample=%s',
                len(records),
                format_sample_record(records),
            )
        finally:
            cnx.close()

    def query_industry_records(self, target_date, existing_start_dates):
        df = self.pro.query('index_classify', level='L1', src='SW2021')
        if df.empty:
            return []
        records = []
        for row in df.to_dict('records'):
            industry_code = self.strip_suffix(row.get('index_code'))
            if not industry_code:
                continue
            records.append({
                'category': self.CATEGORY,
                'index': industry_code,
                'name': str(row.get('industry_name')).strip(),
                'start_date': existing_start_dates.get(industry_code, target_date),
            })
        return records

    def query_industry_stock_records(self, industry_code, target_date):
        df = self.pro.query('index_member_all', l1_code=self.to_tushare_industry_code(industry_code), is_new='Y')
        if df.empty:
            return []
        records = []
        for row in df.to_dict('records'):
            stock_code = self.strip_suffix(row.get('ts_code'))
            if not stock_code:
                continue
            records.append({
                'industry_code': industry_code,
                'date': target_date,
                'code': stock_code,
            })
        return records

    def query_existing_start_dates(self, cnx):
        cursor = cnx.cursor()
        try:
            cursor.execute(
                'SELECT `index`, start_date FROM saa_industries WHERE category = %s',
                (self.CATEGORY,),
            )
            return {
                industry_code: start_date
                for industry_code, start_date in cursor.fetchall()
            }
        finally:
            cursor.close()

    def build_industry_codes(self, industry_codes, cnx):
        if isinstance(industry_codes, str):
            industry_codes = [industry_codes]
        if industry_codes:
            return sorted(industry_codes)

        cursor = cnx.cursor()
        try:
            cursor.execute(
                'SELECT `index` FROM saa_industries WHERE category = %s ORDER BY `index`',
                (self.CATEGORY,),
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()

    def save_industries(self, records, cnx):
        DB().to_sql(records, cnx, 'saa_industries', ['category', 'index'])

    def save_industry_stocks(self, records, cnx):
        DB().to_sql(records, cnx, 'saa_industry_stocks', ['industry_code', 'date', 'code'])

    @staticmethod
    def normalize_target_date(target_date):
        if target_date is None:
            return datetime.today().date()
        if not isinstance(target_date, date_type):
            raise TypeError('target_date must be a date')
        return target_date

    @classmethod
    def normalize_target_dates(cls, target_dates, target_date=None):
        if target_dates is None:
            return [cls.normalize_target_date(target_date)]

        normalized = []
        for value in target_dates:
            if isinstance(value, datetime):
                value = value.date()
            elif not isinstance(value, date_type):
                value = datetime.strptime(str(value), '%Y-%m-%d').date()
            normalized.append(value)
        return normalized

    @staticmethod
    def to_tushare_industry_code(industry_code):
        if not industry_code:
            return industry_code
        industry_code = str(industry_code)
        if '.' in industry_code:
            return industry_code
        return '{}.SI'.format(industry_code)

    @staticmethod
    def strip_suffix(code):
        if pd.isna(code) or code is None:
            return None
        return str(code).split('.')[0].strip()
