# -*- coding: utf-8 -*-
import logging
from datetime import datetime

import akshare
import pandas as pd
from pandas.core.interchange.dataframe_protocol import DataFrame

from saa_collector.services.abstract.quote_service import QuoteService
from .basic_stock_service import BasicStockService


class QuoteServiceImpl(QuoteService, BasicStockService):
    BATCH_SIZE = 50

    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()

    def collect(self, symbols=None, start_date=None):
        df = akshare.stock_zh_a_spot_em()
        if df.empty:
            return

        symbols = self.build_symbols(symbols)

        df = df[df['代码'].isin(symbols)]
        df['symbol'] = df['代码']
        df['price'] = df['最新价']
        df['date'] = datetime.today()
        df = df[['symbol', 'price', 'date']]
        records = df.to_dict('records')
        self._logger.info("Saving %d records to DB", len(records))
        self.save_records(records, 'saa_latest_prices', 'symbol')

    def collect_historical(self, symbols=None, trade_date=None, start_date=None, end_date=None):
        dates = [d for d in [trade_date, start_date, end_date] if d is not None]
        start_date = min(dates)
        end_date = max(dates)
        df = pd.DataFrame()
        for symbol in symbols:
            df1 = akshare.stock_zh_a_hist(
                symbol=symbol, period='monthly',
                start_date=start_date.strftime('%Y%m%d'), end_date=end_date.strftime('%Y%m%d')
            )
            df = pd.concat([df, df1])
        if df.empty:
            return
        existing_symbols = self.build_symbols(symbols)
        df['symbol'] = df['股票代码']
        df['price'] = df['收盘']
        df['date'] = pd.to_datetime(df['日期'], format='%Y%m%d')
        df = df[['symbol', 'price', 'date']]
        df = df[df['symbol'].isin(existing_symbols)]
        records = df.to_dict('records')
        if trade_date is None:
            records = self.filter_records(records, start_date)
        self.save_records(records, 'saa_prices', 'symbol')

    def filter_records(self, records, start_date=None):
        records = [record for record in records if record['date'].month % 3 == 0]
        return records


if __name__ == '__main__':
    QuoteServiceImpl().collect()
