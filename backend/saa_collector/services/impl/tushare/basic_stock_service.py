# -*- coding: utf-8 -*-
import copy
import logging
import math

import mysql.connector

from saa_collector.services.common.config_service import ConfigService
from saa_collector.third_party.tushare_api_client import TushareApiClient
from saa_collector.utils.db import DB
from .basic_service import BasicService


class BasicStockService(BasicService):
    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()
        self.config_service = ConfigService()
        self.config = self.config_service.get_config()
        token = self.config.get('saa_collector').get('tushare_api')['token']
        self.pro = TushareApiClient(token)
        self.db_config = self.config_service.get_db_config()

    def query_records(self, sub_resource, symbols, **kwargs):
        all_raw_records = []
        if isinstance(symbols, str):
            symbols = [symbols]
        for symbol in symbols:
            raw_records = self.query_record(sub_resource, symbol, **kwargs)
            all_raw_records += raw_records
        return all_raw_records

    def query_record(self, sub_resource, symbol, **kwargs):
        df = self.pro.query(sub_resource, ts_code=self.to_code(symbol), **kwargs)
        raw_records = df.to_dict('records')
        return raw_records

    def transform_records(self, raw_records, table):
        table_config_df = self.config_service.get_table_config(table)
        records = []
        for raw_record in raw_records:
            record = self.transform_record(raw_record, table_config_df)
            if not record['date']:
                continue
            record.update({
                'symbol': self.convert_code(record['symbol']),
                'date': self.convert_date(record['date']),
            })
            records.append(record)
        return records

    def filter_records(self, records, start_date=None):
        if not start_date:
            return records
        records = [x for x in records if x['date'] >= start_date]
        return records

    def save_records(self, records, table, primary_keys):
        cnx = mysql.connector.connect(**self.db_config)
        DB().to_sql(records, cnx, table, primary_keys)

    def build_symbols(self, symbols):
        if isinstance(symbols, str):
            symbols = [symbols]
        if not symbols:
            symbols = self.get_symbols_from_db()
        return symbols

    def get_symbols_from_db(self):
        query = "SELECT symbol FROM saa_stocks WHERE type = 'STOCK' AND market = 'A'"
        cnx = mysql.connector.connect(**self.db_config)
        cursor = cnx.cursor()
        cursor.execute(query)
        symbols = [i[0] for i in cursor.fetchall()]
        symbols.sort()
        return symbols

    def build_code_param(self, symbols):
        if not symbols:
            return None
        if isinstance(symbols, list):
            if len(symbols) == 0:
                return None
            codes = [self.to_code(symbol) for symbol in symbols]
            return codes
        return symbols

    def build_date_param(self, date):
        if date is None:
            return date
        return date.strftime('%Y%m%d')

    def transform_record(self, raw_record, table_config_df):
        record = {}
        for index, row in table_config_df.iterrows():
            ts_field = row['TushareField']
            if ts_field == '' or (isinstance(ts_field, (int, float)) and math.isnan(ts_field)):
                continue
            value = raw_record[ts_field]
            unit = row.get('TushareUnit', 1)
            unit = 1 if math.isnan(unit) else unit
            record[row['Field']] = None if value is None else value * unit
        return record

    def to_code(self, symbol):
        prefix = symbol[0:1]
        if prefix == '6':
            suffix = 'SH'
        else:
            suffix = 'SZ'
        return "{}.{}".format(symbol, suffix)

    def convert_code(self, code):
        if not code:
            return code
        return code[0:-3]

    def convert_date(self, date):
        if not date:
            return date
        return "{}-{}-{}".format(date[:4], date[4:6], date[6:])

    def to_sql(self, rows, cnx, table, primary_keys):
        if len(rows) == 0:
            return
        fields = list(rows[0].keys())
        normal_fields = copy.deepcopy(fields)
        normal_fields = [k for k in normal_fields if k not in primary_keys]
        update_statements = []
        for field in normal_fields:
            update_statements.append("{} = VALUES({})".format(field, field))
        update_statement = ", ".join(update_statements)
        sql = "INSERT INTO {} ({}) VALUES ({}) ON DUPLICATE KEY UPDATE {}".format(
            table, ", ".join(fields), ", ".join(["%s"] * len(fields)), update_statement
        )
        cursor = cnx.cursor(prepared=True)
        for stock_info in rows:
            try:
                values = stock_info.values()
                values = [None if v is None else str(v) for v in values]
                cursor.execute(sql, tuple(values))
            except:
                self._logger.error('Failed to execute sql for %s', stock_info)
                raise
        cnx.commit()
