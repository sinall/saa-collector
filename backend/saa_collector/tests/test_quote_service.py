from unittest.mock import MagicMock

import pandas as pd
from django.test import SimpleTestCase

from saa_collector.constants import DATA_TYPE_CONFIG
from saa_collector.services.impl.tushare.quote_service import QuoteServiceImpl


class TushareQuoteServiceTest(SimpleTestCase):
    def _make_service(self):
        service = QuoteServiceImpl.__new__(QuoteServiceImpl)
        service._logger = MagicMock()
        service.pro = MagicMock()
        service.build_symbols = MagicMock(return_value=['000001', '000002', '000003'])
        service.save_records = MagicMock()
        return service

    def test_historical_quote_is_configured_as_monthly_source_data(self):
        config = DATA_TYPE_CONFIG['historical_quote']

        self.assertEqual(config['table'], 'saa_prices_ex')
        self.assertEqual(config['date_column'], 'date')
        self.assertEqual(config['stock_column'], 'code')
        self.assertEqual(config['data_frequency'], 'monthly')
        self.assertEqual(config['label'], '历史行情')

    def test_price_adjust_factor_is_configured_as_monthly_source_data(self):
        config = DATA_TYPE_CONFIG['price_adjust_factor']

        self.assertEqual(config['table'], 'saa_price_adjust_factors')
        self.assertEqual(config['date_column'], 'date')
        self.assertEqual(config['stock_column'], 'code')
        self.assertEqual(config['data_frequency'], 'monthly')
        self.assertEqual(config['label'], '复权因子')

    def test_collect_saves_latest_quotes_without_quarter_filtering(self):
        service = self._make_service()
        service.pro.query.return_value = pd.DataFrame([
            {'ts_code': '000001.SZ', 'close': 10.5, 'trade_date': '20260526'},
            {'ts_code': '000002.SZ', 'close': 11.5, 'trade_date': '20260526'},
        ])

        service.collect()

        service.save_records.assert_called_once()
        records = service.save_records.call_args.args[0]
        self.assertEqual(len(records), 2)
        self.assertEqual([record['symbol'] for record in records], ['000001', '000002'])
        self.assertEqual([record['date'] for record in records], ['2026-05-26', '2026-05-26'])
        self.assertEqual(service.save_records.call_args.args[1:], ('saa_latest_prices', 'symbol'))

    def test_filter_records_keeps_all_monthly_records(self):
        service = self._make_service()

        records = service.filter_records([
            {'code': '000001', 'close': 10.5, 'date': '2026-03-31'},
            {'code': '000002', 'close': 11.5, 'date': '2026-05-26'},
            {'code': '000003', 'close': 12.5, 'date': '2026-06-30'},
        ])

        self.assertEqual([record['code'] for record in records], ['000001', '000002', '000003'])

    def test_collect_historical_saves_monthly_ohlcv_records(self):
        service = self._make_service()
        service.pro.monthly.return_value = pd.DataFrame([
            {
                'ts_code': '000001.SZ',
                'open': 10.0,
                'close': 10.5,
                'high': 10.8,
                'low': 9.9,
                'vol': 1000,
                'amount': 10500,
                'trade_date': '20260331',
            },
            {
                'ts_code': '000002.SZ',
                'open': 11.0,
                'close': 11.5,
                'high': 11.8,
                'low': 10.9,
                'vol': 2000,
                'amount': 23000,
                'trade_date': '20260529',
            },
            {
                'ts_code': '000003.SZ',
                'open': 12.0,
                'close': 12.5,
                'high': 12.8,
                'low': 11.9,
                'vol': 3000,
                'amount': 37500,
                'trade_date': '20260630',
            },
        ])

        service.collect_historical(
            symbols=['000001', '000002', '000003'],
            start_date=pd.Timestamp('2026-03-01'),
            end_date=pd.Timestamp('2026-06-30'),
        )

        service.pro.monthly.assert_called_once()
        query_kwargs = service.pro.monthly.call_args.kwargs
        self.assertEqual(query_kwargs['ts_code'], ['000001', '000002', '000003'])
        self.assertEqual(query_kwargs['start_date'], '20260301')
        self.assertEqual(query_kwargs['end_date'], '20260630')
        self.assertNotIn('trade_date', query_kwargs)

        service.save_records.assert_called_once()
        records = service.save_records.call_args.args[0]
        self.assertEqual([record['code'] for record in records], ['000001', '000002', '000003'])
        self.assertEqual(records[0], {
            'code': '000001',
            'date': '2026-03-31',
            'open': 10.0,
            'close': 10.5,
            'high': 10.8,
            'low': 9.9,
            'volume': 1000,
            'money': 10500,
            'paused': 0,
        })
        self.assertEqual(service.save_records.call_args.args[1:], ('saa_prices_ex', ['code', 'date']))

    def test_collect_historical_queries_monthly_quotes_in_symbol_batches(self):
        service = self._make_service()
        symbols = [f'{index:06d}' for index in range(1, 53)]
        service.build_symbols.return_value = symbols
        service.pro.monthly.side_effect = [
            pd.DataFrame([
                {
                    'ts_code': '000001.SZ',
                    'open': 10.0,
                    'close': 10.5,
                    'high': 10.8,
                    'low': 9.9,
                    'vol': 1000,
                    'amount': 10500,
                    'trade_date': '20260430',
                },
            ]),
            pd.DataFrame([
                {
                    'ts_code': '000051.SZ',
                    'open': 11.0,
                    'close': 11.5,
                    'high': 11.8,
                    'low': 10.9,
                    'vol': 2000,
                    'amount': 23000,
                    'trade_date': '20260430',
                },
            ]),
        ]

        service.collect_historical(
            symbols=symbols,
            start_date=pd.Timestamp('2026-04-01'),
            end_date=pd.Timestamp('2026-04-30'),
        )

        self.assertEqual(service.pro.monthly.call_count, 2)
        first_call = service.pro.monthly.call_args_list[0].kwargs
        second_call = service.pro.monthly.call_args_list[1].kwargs
        self.assertEqual(first_call['ts_code'], symbols[:50])
        self.assertEqual(second_call['ts_code'], symbols[50:])
        service.save_records.assert_called_once()
        records = service.save_records.call_args.args[0]
        self.assertEqual([record['code'] for record in records], ['000001', '000051'])

    def test_collect_historical_queries_monthly_quotes_by_trade_date_for_scoped_month(self):
        service = self._make_service()
        service.pro.monthly.return_value = pd.DataFrame([
            {
                'ts_code': '000001.SZ',
                'open': 10.0,
                'close': 10.5,
                'high': 10.8,
                'low': 9.9,
                'vol': 1000,
                'amount': 10500,
                'trade_date': '20260430',
            },
            {
                'ts_code': '600000.SH',
                'open': 12.0,
                'close': 12.5,
                'high': 12.8,
                'low': 11.9,
                'vol': 3000,
                'amount': 37500,
                'trade_date': '20260430',
            },
        ])

        service.collect_historical(
            symbols=['000001'],
            trade_date=pd.Timestamp('2026-04-30'),
            start_date=pd.Timestamp('2026-04-01'),
            end_date=pd.Timestamp('2026-04-30'),
        )

        service.pro.monthly.assert_called_once_with(trade_date='20260430')
        service.save_records.assert_called_once()
        records = service.save_records.call_args.args[0]
        self.assertEqual([record['code'] for record in records], ['000001'])

    def test_collect_adjust_factors_saves_monthly_adjustment_records(self):
        service = self._make_service()
        service.pro.query.return_value = pd.DataFrame([
            {'ts_code': '000001.SZ', 'trade_date': '20260331', 'adj_factor': 145.32},
            {'ts_code': '000002.SZ', 'trade_date': '20260331', 'adj_factor': 98.76},
            {'ts_code': '000004.SZ', 'trade_date': '20260331', 'adj_factor': 12.34},
        ])

        service.collect_adjust_factors(
            symbols=['000001', '000002', '000003'],
            start_date=pd.Timestamp('2026-03-01'),
            end_date=pd.Timestamp('2026-03-31'),
        )

        service.pro.query.assert_called_once_with(
            'stk_factor',
            ts_code=['000001', '000002', '000003'],
            start_date='20260301',
            end_date='20260331',
            fields='ts_code,trade_date,adj_factor',
        )
        service.save_records.assert_called_once()
        records = service.save_records.call_args.args[0]
        self.assertEqual(records, [
            {'code': '000001', 'date': '2026-03-31', 'adj_factor': 145.32},
            {'code': '000002', 'date': '2026-03-31', 'adj_factor': 98.76},
        ])
        self.assertEqual(
            service.save_records.call_args.args[1:],
            ('saa_price_adjust_factors', ['code', 'date']),
        )
