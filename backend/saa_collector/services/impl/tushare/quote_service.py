# -*- coding: utf-8 -*-
import logging
from datetime import datetime

import pandas as pd

from saa_collector.services.abstract.quote_service import QuoteService
from .basic_stock_service import BasicStockService


class QuoteServiceImpl(QuoteService, BasicStockService):
    BATCH_SIZE = 50
    ADJUST_FACTOR_FIELDS = 'ts_code,trade_date,adj_factor'

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
        symbols = self.build_symbols(symbols)

        base_query_kwargs = {
            'start_date': start_date.strftime('%Y%m%d') if start_date else None,
            'end_date': end_date.strftime('%Y%m%d') if end_date else None,
        }
        all_frames = []
        if trade_date is not None:
            query_kwargs = {
                'trade_date': trade_date.strftime('%Y%m%d'),
            }
            self._logger.info(
                "Querying Tushare monthly quotes by trade_date: symbols=%d trade_date=%s symbols_sample=%s",
                len(symbols),
                query_kwargs.get('trade_date'),
                symbols[:5],
            )
            df = self.pro.monthly(**query_kwargs)
            if df.empty:
                self._logger.warning(
                    "No Tushare monthly quotes returned by trade_date: symbols=%d trade_date=%s symbols_sample=%s",
                    len(symbols),
                    query_kwargs.get('trade_date'),
                    symbols[:5],
                )
                return
            all_frames.append(df)
        else:
            symbol_batches = [
                symbols[index:index + self.BATCH_SIZE]
                for index in range(0, len(symbols), self.BATCH_SIZE)
            ]
            for batch_index, batch in enumerate(symbol_batches, start=1):
                query_kwargs = {
                    **base_query_kwargs,
                    'ts_code': batch,
                }
                self._logger.info(
                    "Querying Tushare monthly quotes: batch=%d/%d symbols=%d "
                    "start_date=%s end_date=%s symbols_sample=%s",
                    batch_index,
                    len(symbol_batches),
                    len(batch),
                    query_kwargs.get('start_date'),
                    query_kwargs.get('end_date'),
                    batch[:5],
                )
                batch_df = self.pro.monthly(**query_kwargs)
                if batch_df.empty:
                    self._logger.warning(
                        "No Tushare monthly quotes returned: batch=%d/%d symbols=%d "
                        "start_date=%s end_date=%s symbols_sample=%s",
                        batch_index,
                        len(symbol_batches),
                        len(batch),
                        query_kwargs.get('start_date'),
                        query_kwargs.get('end_date'),
                        batch[:5],
                    )
                    continue
                all_frames.append(batch_df)

        if not all_frames:
            self._logger.warning(
                "No Tushare monthly quotes returned for all batches: symbols=%d "
                "start_date=%s end_date=%s trade_date=%s",
                len(symbols),
                base_query_kwargs.get('start_date'),
                base_query_kwargs.get('end_date'),
                trade_date.strftime('%Y%m%d') if trade_date is not None else None,
            )
            return

        df = pd.concat(all_frames, ignore_index=True)
        if df.empty:
            self._logger.warning(
                "No Tushare monthly quotes returned: symbols=%d start_date=%s end_date=%s trade_date=%s",
                len(symbols),
                base_query_kwargs.get('start_date'),
                base_query_kwargs.get('end_date'),
                trade_date.strftime('%Y%m%d') if trade_date is not None else None,
            )
            return

        df['code'] = df['ts_code'].apply(lambda x: x.split('.')[0])
        df = df[df['code'].isin(symbols)].copy()
        if df.empty:
            self._logger.warning(
                "Tushare monthly quotes returned no requested symbols after filtering: symbols=%d "
                "start_date=%s end_date=%s trade_date=%s symbols_sample=%s",
                len(symbols),
                base_query_kwargs.get('start_date'),
                base_query_kwargs.get('end_date'),
                trade_date.strftime('%Y%m%d') if trade_date is not None else None,
                symbols[:5],
            )
            return
        df['date'] = df['trade_date'].apply(lambda x: "{}-{}-{}".format(x[:4], x[4:6], x[6:]))
        df['volume'] = df.get('vol')
        df['money'] = df.get('amount')
        df['paused'] = 0
        df = df[['code', 'date', 'open', 'close', 'high', 'low', 'volume', 'money', 'paused']]
        records = df.to_dict('records')
        records = self.filter_records(records, start_date)
        self._logger.info(
            "Saving %d Tushare monthly quote records to saa_prices_ex: symbols=%d start_date=%s end_date=%s",
            len(records),
            len(symbols) if symbols else 0,
            start_date,
            end_date,
        )
        self.save_records(records, 'saa_prices_ex', ['code', 'date'])

    def collect_adjust_factors(self, symbols=None, trade_date=None, start_date=None, end_date=None):
        dates = [d for d in [trade_date, start_date, end_date] if d is not None]
        if not dates:
            return

        start_date = min(dates)
        end_date = max(dates)
        symbols = self.build_symbols(symbols)
        query_kwargs = {
            'fields': self.ADJUST_FACTOR_FIELDS,
        }
        if trade_date is not None:
            query_kwargs['trade_date'] = trade_date.strftime('%Y%m%d')
        else:
            query_kwargs['start_date'] = start_date.strftime('%Y%m%d') if start_date else None
            query_kwargs['end_date'] = end_date.strftime('%Y%m%d') if end_date else None

        self._logger.info(
            "Querying Tushare stock adjustment factors: symbols=%d start_date=%s end_date=%s trade_date=%s",
            len(symbols),
            query_kwargs.get('start_date'),
            query_kwargs.get('end_date'),
            query_kwargs.get('trade_date'),
        )
        df = self.pro.query('adj_factor', **query_kwargs)
        if df.empty:
            self._logger.warning(
                "No Tushare stock adjustment factors returned: symbols=%d start_date=%s end_date=%s trade_date=%s",
                len(symbols),
                query_kwargs.get('start_date'),
                query_kwargs.get('end_date'),
                query_kwargs.get('trade_date'),
            )
            return

        df['code'] = df['ts_code'].apply(lambda x: x.split('.')[0])
        df = df[df['code'].isin(symbols)].copy()
        if df.empty:
            self._logger.warning(
                "Tushare adjustment factors returned no requested symbols after filtering: symbols=%d",
                len(symbols),
            )
            return

        df['date'] = df['trade_date'].apply(lambda x: "{}-{}-{}".format(x[:4], x[4:6], x[6:]))
        df = df.rename(columns={'adj_factor': 'adj_factor'})
        df = df[['code', 'date', 'adj_factor']]
        records = df.to_dict('records')
        records = self.filter_records(records, start_date)
        self._logger.info(
            "Saving %d Tushare adjustment factor records to saa_price_adjust_factors: symbols=%d",
            len(records),
            len(symbols),
        )
        self.save_records(records, 'saa_price_adjust_factors', ['code', 'date'])

    def filter_records(self, records, start_date=None):
        return [record for record in records if record.get('date') is not None]


if __name__ == '__main__':
    QuoteServiceImpl().collect()
