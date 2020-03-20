# -*- coding: utf-8 -*-
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
            'SZSE': 'SZ',
            'SSE': 'SH'
        }
        board_dict = {
            '': 'MAIN_BOARD',
            '主板': 'MAIN_BOARD',
            '中小板': 'SMALL_AND_MEDIUM_ENTERPRISES',
            '创业板': 'CHINEXT',
            '科创板': 'STAR'
        }
        raw_records = self.query_records(
            'stock_basic', scode_list, fields='ts_code,symbol,name,area,industry,list_date,market,exchange'
        )
        stock_info_dict = {}
        for raw_record in raw_records:
            list_date = raw_record['list_date']
            stock_info = {
                'symbol': raw_record['symbol'],
                'name': raw_record['name'],
                'exchange': exchange_dict[raw_record['exchange']],
                'board': board_dict[raw_record['market']],
                'listing_time': "{}-{}-{}".format(list_date[:4], list_date[4:6], list_date[6:]),
            }
            stock_info_dict[stock_info['symbol']] = stock_info

        table_config_df = self.xls_file.parse('saa_stocks')
        company_records = self.query_records(
            'stock_company', scode_list, fields='ts_code,exchange,introduction,chairman,secretary,reg_capital,website'
        )
        company_info_dict = {}
        for raw_record in company_records:
            stock_info = self.transform_record(raw_record, table_config_df)
            stock_info.update({
                'symbol': self.convert_code(stock_info['symbol']),
            })
            company_info_dict[stock_info['symbol']] = stock_info

        for symbol, stock_info in stock_info_dict.items():
            stock_info.update(company_info_dict[symbol])
        return list(stock_info_dict.values())
