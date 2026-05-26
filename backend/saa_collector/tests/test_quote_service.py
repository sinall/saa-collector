from unittest.mock import MagicMock

import pandas as pd
from django.test import SimpleTestCase

from saa_collector.services.impl.tushare.quote_service import QuoteServiceImpl


class TushareQuoteServiceTest(SimpleTestCase):
    def _make_service(self):
        service = QuoteServiceImpl.__new__(QuoteServiceImpl)
        service._logger = MagicMock()
        service.pro = MagicMock()
        service.build_symbols = MagicMock(return_value=['000001', '000002', '000003'])
        service.save_records = MagicMock()
        return service

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
        self.assertEqual([record['code'] for record in records], ['000001', '000002'])
        self.assertEqual([record['date'] for record in records], ['2026-05-26', '2026-05-26'])

    def test_filter_records_accepts_string_dates(self):
        service = self._make_service()

        records = service.filter_records([
            {'code': '000001', 'price': 10.5, 'date': '2026-03-31'},
            {'code': '000002', 'price': 11.5, 'date': '2026-05-26'},
            {'code': '000003', 'price': 12.5, 'date': '2026-06-30'},
        ])

        self.assertEqual([record['code'] for record in records], ['000001', '000003'])

    def test_collect_historical_uses_date_range_without_trade_date(self):
        service = self._make_service()
        service.pro.monthly.return_value = pd.DataFrame([
            {'ts_code': '000001.SZ', 'close': 10.5, 'trade_date': '20260331'},
            {'ts_code': '000002.SZ', 'close': 11.5, 'trade_date': '20260526'},
            {'ts_code': '000003.SZ', 'close': 12.5, 'trade_date': '20260630'},
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
        self.assertEqual([record['code'] for record in records], ['000001', '000003'])
