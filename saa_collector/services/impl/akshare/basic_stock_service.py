# -*- coding: utf-8 -*-
import copy
import logging
import math
from datetime import datetime

import mysql.connector
import pandas as pd

from saa_collector.services.common.config_service import ConfigService
from saa_collector.utils.db import DB
from .basic_service import BasicService
import akshare as ak

class BasicStockService(BasicService):
    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()
        self.config_service = ConfigService()
        self.config = self.config_service.get_config()
        self.db_config = self.config_service.get_db_config()
        self.resource_table_mapping = {
            'stock': 'saa_stocks',
            'balance_sheet': 'saa_raw_balance_sheet',
            'income_statement': 'saa_raw_income_statement',
            'cash_flow_statement': 'saa_raw_cash_flow_statement',
            'dividend': 'saa_dividends',
            'capital': 'saa_capitals',
            'main_business': 'saa_raw_main_business',
        }
        self.channel = 'AkshareField'

    def query_records(self, sub_resource, symbols, **kwargs):
        all_raw_records = []
        if isinstance(symbols, str):
            symbols = [symbols]
        for symbol in symbols:
            raw_records = self.query_record(sub_resource, symbol, **kwargs)
            all_raw_records += raw_records
        return all_raw_records

    def query_record(self, sub_resource, symbol, **kwargs):
        df = ak.stock_individual_info_em(symbol=self.to_code(symbol), **kwargs)
        raw_records = [df.set_index('item')['value'].to_dict()]
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

    def query(self, sub_resource, symbols, channel, start_date, **kwargs):
        all_df = pd.DataFrame()
        if isinstance(symbols, str):
            symbols = [symbols]
        for symbol in symbols:
            df = self.query_one(sub_resource, symbol, **kwargs)
            df = self.transform(df, sub_resource, symbol, channel)
            df = self.filter(df, start_date)
            all_df = pd.concat([all_df, df], axis=0)
        return all_df

    def query_one(self, sub_resource, symbol, **kwargs):
        pass

    def filter(self, df, start_date, **kwargs):
        if not isinstance(start_date, (datetime, pd.Timestamp)):
            try:
                start_date = pd.to_datetime(start_date)
            except:
                raise ValueError("无法解析start_date，请提供有效的日期格式")
        df['_temp_date'] = pd.to_datetime(df['date'], errors='coerce')
        valid_dates = df[df['_temp_date'].notna()]
        result = valid_dates[valid_dates['_temp_date'] >= start_date].copy()
        result.drop('_temp_date', axis=1, inplace=True)
        return result

    def transform(self, df, sub_resource, symbol, channel):
        table = self._get_table(sub_resource)
        table_config_df = self.config_service.get_table_config(table)
        new_df = pd.DataFrame(index=df.index)
        new_df['symbol'] = symbol
        for index, row in table_config_df.iterrows():
            column = row['Field']
            if column in ['id', 'symbol']:
                continue
            new_df[column] = None
            if pd.isna(row[channel]):
                continue
            try:
                new_df[column] = self.eval_expr(df, row[channel])
            except Exception as e:
                self._logger.error('Failed to eval_expr(%s) for %s of %s because: %s',
                                   row[channel], sub_resource, symbol, str(e))
                pass
        return new_df

    def eval_expr(self, df, expr):
        if expr in df.columns:
            return df[expr]
        if '|' in expr:
            cols = [col.strip() for col in expr.split('|')]
            for col in cols:
                if col in df.columns:
                    return df[col]
            return None
        return df.eval(expr)

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
        elif isinstance(symbols, pd.DataFrame):
            if symbols.empty:
                symbols = self.get_symbols_from_db()
            else:
                symbols = symbols['symbol'].tolist()
        elif not symbols:
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
            field = row['AkshareField']
            if field == '' or (isinstance(field, (int, float)) and math.isnan(field)):
                continue
            fields = field.split("|")
            for field in fields:
                if not field in raw_record:
                    continue
                value = raw_record[field]
                unit = row.get('AkshareUnit')
                if not pd.isna(unit):
                    value *= unit
                record[row['Field']] = value
                break
        return record

    def to_code(self, symbol):
        return symbol

    def convert_code(self, code):
        if not code:
            return code
        if len(code) < 3 or code[-3] != '.':
            return code
        return code[0:-3]

    def convert_date(self, date):
        if not isinstance(date, str):
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

    def _get_table(self, sub_resource):
        return self.resource_table_mapping.get(sub_resource)
