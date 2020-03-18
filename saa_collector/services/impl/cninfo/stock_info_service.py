# -*- coding: utf-8 -*-
import re
import time

import mysql.connector

from saa_collector.services.abstract.stock_info_service import StockInfoService
from saa_collector.third_party.cninfo_api_client import CninfoApiClient
from saa_collector.utils.db import DB
from .basic_stock_service import BasicStockService


class StockInfoServiceImpl(StockInfoService, BasicStockService):
    def __init__(self):
        super().__init__()
        api_config = self.config.get('saa_collector').get('cninfo_api')
        self.client = CninfoApiClient(api_config['client_id'], api_config['client_secret'])
        self.db_config = self.config.get('saa_collector').get('db')

    def collect(self, symbols):
        start_time = time.time()
        self.client.login()
        symbols = self.build_symbols(symbols)
        records = self.get_stock_info_list(symbols)
        cnx = mysql.connector.connect(**self.db_config)
        DB().to_sql(records, cnx, 'saa_stocks', 'symbol')
        print("--- %s seconds ---" % int(time.time() - start_time))

    def build_symbols(self, symbols):
        if isinstance(symbols, str):
            symbols = [symbols]
        if not symbols:
            plate_response = self.client.get_plate_stock_list('137001')
            plate_stock_list = plate_response['records']
            symbols = [v['SECCODE'] for v in plate_stock_list]
        return symbols

    def get_stock_info_list(self, scode_list):
        exchange_dict = {
            '深交所': 'SZ',
            '上交所': 'SH'
        }
        board_dict = {
            '': 'MAIN_BOARD',
            '主板': 'MAIN_BOARD',
            '中小板': 'SMALL_AND_MEDIUM_ENTERPRISES',
            '创业板': 'CHINEXT',
            '科创板': 'STAR'
        }
        stock_records = self.query_records(scode_list, 'p_stock2101')
        stock_info_dict = {}
        for record in stock_records:
            match = re.match(r'(.*所)(.*)', record['F005V'])
            stock_info = {
                'symbol': record['SECCODE'],
                'exchange': exchange_dict[match.group(1)],
                'board': board_dict[match.group(2)],
                'issue_quantity': record['F007N'],
                'listing_time': record['F006D'],
            }
            stock_info_dict[stock_info['symbol']] = stock_info

        table_config_df = self.xls_file.parse('saa_stocks')
        company_records = self.query_records(scode_list, 'p_stock2100')
        company_info_dict = {}
        for raw_record in company_records:
            stock_info = self.transform_record(raw_record, table_config_df)
            company_info_dict[stock_info['symbol']] = stock_info

        for symbol, stock_info in stock_info_dict.items():
            stock_info.update(company_info_dict[symbol])
        return list(stock_info_dict.values())
