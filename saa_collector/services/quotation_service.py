# -*- coding: utf-8 -*-
import datetime
import logging

import mysql.connector

from saa_collector.services.basic_stock_service import BasicStockService
from saa_collector.utils.db import DB


class QuotationService(BasicStockService):
    BATCH_SIZE = 50

    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()

    def collect(self, symbols=None):
        today = datetime.datetime.today()
        today = today.strftime('%Y%m%d')
        df = self.pro.daily(trade_date=today)
        if df.empty:
            return

        symbols = self.build_symbols(symbols)

        df['symbol'] = df['ts_code'].apply(lambda x: x.split('.')[0])
        df = df[df['symbol'].isin(symbols)]
        df['price'] = df['close']
        df['date'] = df['trade_date'].apply(lambda x: "{}-{}-{}".format(x[:4], x[4:6], x[6:]))
        df = df[['symbol', 'price', 'date']]
        records = df.to_dict('records')
        self._logger.info("Saving %d records to DB", len(records))
        cnx = mysql.connector.connect(**self.db_config)
        DB().to_sql(records, cnx, 'saa_latest_prices', 'symbol')

    def collect_historical(self, symbols=None, trade_date=None, start_date=None, end_date=None):
        df = self.pro.monthly(
            ts_code=symbols, trade_date=trade_date.strftime('%Y%m%d'),
            start_date=start_date, end_date=end_date
        )
        if df.empty:
            return
        symbols = self.build_symbols(symbols)
        df['symbol'] = df['ts_code'].apply(lambda x: x.split('.')[0])
        df = df[df['symbol'].isin(symbols)]
        df['price'] = df['close']
        df['date'] = df['trade_date'].apply(lambda x: "{}-{}-{}".format(x[:4], x[4:6], x[6:]))
        df = df[['symbol', 'price', 'date']]
        records = df.to_dict('records')
        cnx = mysql.connector.connect(**self.db_config)
        DB().to_sql(records, cnx, 'saa_prices', 'symbol')


if __name__ == '__main__':
    QuotationService().collect()
