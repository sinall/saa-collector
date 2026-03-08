# -*- coding: utf-8 -*-
import copy
import math
import time

import mysql.connector

from saa_collector.services.common.config_service import ConfigService
from saa_collector.third_party.cninfo_api_client import CninfoApiClient
from saa_collector.third_party.cninfo_api_client import CninfoApiException
from saa_collector.third_party.tushare_api_client import TushareApiClient
from saa_collector.utils.db import DB
from .basic_service import BasicService


class BasicStockService(BasicService):
    def __init__(self):
        super().__init__()
        self.config_service = ConfigService()
        self.config = self.config_service.get_config()
        api_config = self.config.get('saa_collector').get('cninfo_api')
        self.client = CninfoApiClient(api_config['client_id'], api_config['client_secret'])
        token = self.config.get('saa_collector').get('tushare_api')['token']
        self.pro = TushareApiClient(token)
        self.db_config = self.config_service.get_db_config()

    def query_records(self, symbols, sub_resource, **kwargs):
        self.client.login()
        batch_size = CninfoApiClient.BATCH_SIZE
        symbol_chunks = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
        chunk_index = 0
        fail_round = 0
        raw_records = []
        while chunk_index < len(symbol_chunks):
            try:
                symbol_chunk = symbol_chunks[chunk_index]
                response = self.client.get_stock_info(sub_resource, symbol_chunk, **kwargs)
                batch_raw_records = response['records']
                raw_records.extend(batch_raw_records)
                chunk_index += 1
                time.sleep(1)
            except CninfoApiException:
                if fail_round > len(symbol_chunks):
                    raise
                fail_round += 1
                self.client.login()
        return raw_records

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

    def build_start_date(self, start_date):
        return start_date.strftime('%Y%m%d')

    def transform_records(self, raw_records, table):
        table_config_df = self.config_service.get_table_config(table)
        records = []
        for raw_record in raw_records:
            record = self.transform_record(raw_record, table_config_df)
            if not record['date']:
                continue
            records.append(record)
        return records

    def transform_record(self, raw_record, table_config_df):
        record = {}
        for index, row in table_config_df.iterrows():
            cninfo_field = row['CninfoField']
            if cninfo_field == '' or (isinstance(cninfo_field, (int, float)) and math.isnan(cninfo_field)):
                continue
            value = raw_record[cninfo_field]
            unit = row.get('CninfoUnit', 1)
            unit = 1 if math.isnan(unit) else unit
            record[row['Field']] = None if value is None else value * unit
        return record

    def filter_records(self, records, start_date=None):
        if not start_date:
            return records
        records = [x for x in records if x['date'] >= start_date]
        return records

    def save_records(self, records, table, primary_keys):
        cnx = mysql.connector.connect(**self.db_config)
        DB().to_sql(records, cnx, table)

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
                print(stock_info)
                raise
        cnx.commit()
