# -*- coding: utf-8 -*-
import logging
from datetime import datetime

import pandas as pd

from saa_collector.services.abstract.quote_service import QuoteService
from .basic_stock_service import BasicStockService


class QuoteServiceImpl(QuoteService, BasicStockService):
    BATCH_SIZE = 50

    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()

    def collect(self, symbols=None, start_date=None):
        today = datetime.today().strftime('%Y%m%d')
        df = self.pro.query('daily', trade_date=today)
        if df.empty:
            return

        symbols = self.build_symbols(symbols)

        df['symbol'] = df['ts_code'].apply(lambda x: x.split('.')[0])
        df = df[df['symbol'].isin(symbols)].copy()
        df['price'] = df['close']
        df['date'] = df['trade_date'].apply(lambda x: "{}-{}-{}".format(x[:4], x[4:6], x[6:]))
        df = df[['symbol', 'price', 'date']]
        records = df.to_dict('records')
        self._logger.info("Saving %d records to DB", len(records))
        self.save_records(records, 'saa_latest_prices', 'symbol')

    def collect_historical(self, symbols=None, trade_date=None, start_date=None, end_date=None):
        dates = [d for d in [trade_date, start_date, end_date] if d is not None]
        if not dates:
            return

        start_date = min(dates)
        end_date = max(dates)
        query_kwargs = {
            'ts_code': symbols,
            'start_date': start_date.strftime('%Y%m%d') if start_date else None,
            'end_date': end_date.strftime('%Y%m%d') if end_date else None,
        }
        if trade_date is not None:
            query_kwargs['trade_date'] = trade_date.strftime('%Y%m%d')

        df = self.pro.monthly(**query_kwargs)
        if df.empty:
            return

        symbols = self.build_symbols(symbols)
        df['code'] = df['ts_code'].apply(lambda x: x.split('.')[0])
        df = df[df['code'].isin(symbols)].copy()
        df['price'] = df['close']
        df['date'] = df['trade_date'].apply(lambda x: "{}-{}-{}".format(x[:4], x[4:6], x[6:]))
        df = df[['code', 'price', 'date']]
        records = df.to_dict('records')
        records = self.filter_records(records, start_date)
        self.save_records(records, 'saa_prices_ex', 'code')

    def filter_records(self, records, start_date=None):
        filtered_records = []
        for record in records:
            record_date = record.get('date')
            if isinstance(record_date, str):
                record_date = datetime.strptime(record_date, '%Y-%m-%d').date()
            if record_date is None:
                continue
            if record_date.month % 3 == 0:
                filtered_records.append(record)
        return filtered_records


if __name__ == '__main__':
    QuoteServiceImpl().collect()
