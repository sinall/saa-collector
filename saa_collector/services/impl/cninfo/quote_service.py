# -*- coding: utf-8 -*-
import datetime
import logging

from saa_collector.services.abstract.quote_service import QuoteService
from .basic_stock_service import BasicStockService


class QuoteServiceImpl(QuoteService, BasicStockService):
    BATCH_SIZE = 50

    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()

    def collect(self, symbols=None):
        today = datetime.datetime.today()
        today = today.strftime('%Y%m%d')
        df = self.pro.query('daily', trade_date=today)
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
        self.save_records(records, 'saa_latest_prices', 'symbol')

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
        records = self.filter_records(records, start_date)
        self.save_records(records, 'saa_prices', 'symbol')

    def filter_records(self, records, start_date=None):
        records = [record for record in records if record['date'].month() % 3 is 0]
        return records


if __name__ == '__main__':
    QuoteService().collect()
