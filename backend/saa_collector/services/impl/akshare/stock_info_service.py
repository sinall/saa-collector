# -*- coding: utf-8 -*-
import logging
import time

import mysql.connector

from saa_collector.services.abstract.stock_info_service import StockInfoService
from saa_collector.utils.db import DB
from .basic_stock_service import BasicStockService
from ...common.stock_utils import StockUtils
import akshare as ak


class StockInfoServiceImpl(StockInfoService, BasicStockService):
    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()
        self.db_config = self.config.get('saa_collector').get('db')

    def collect(self, symbols):
        start_time = time.time()
        symbols = self.build_symbols(symbols)
        records = self.get_stock_info_list(symbols)
        cnx = mysql.connector.connect(**self.db_config)
        DB().to_sql(records, cnx, 'saa_stocks', 'symbol')
        self._logger.info("--- %s seconds ---", int(time.time() - start_time))

    def build_symbols(self, symbols):
        if isinstance(symbols, str):
            symbols = [symbols]
        if not symbols:
            df = ak.stock_info_a_code_name()
            symbols = df['code'].tolist()
        return symbols

    def get_stock_info_list(self, scode_list):
        raw_records = self.query_records(
            'stock_basic', scode_list
        )
        stock_info_dict = {}
        for raw_record in raw_records:
            list_date = str(raw_record['上市时间'])
            symbol = raw_record['股票代码']
            name = raw_record['股票简称']
            stock_info = {
                'symbol': symbol,
                'name': name,
                'exchange': str(StockUtils.to_exchange(symbol)),
                'board': str(StockUtils.to_board(symbol, name)),
                'listing_time': "{}-{}-{}".format(list_date[:4], list_date[4:6], list_date[6:]),
            }
            stock_info_dict[stock_info['symbol']] = stock_info
        return list(stock_info_dict.values())
