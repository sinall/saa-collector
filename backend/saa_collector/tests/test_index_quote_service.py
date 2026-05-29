from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
from django.test import SimpleTestCase

from saa_collector.services.common.index_quote_service import IndexQuoteService


class IndexQuoteServiceTest(SimpleTestCase):
    @patch('saa_collector.services.common.index_quote_service.ConfigService')
    @patch('saa_collector.services.common.index_quote_service.get_tushare_client')
    @patch('saa_collector.services.common.index_quote_service.mysql.connector.connect')
    @patch('saa_collector.services.common.index_quote_service.DB')
    def test_collect_saves_index_daily_quotes(self, db_class, connect, get_client, config_service_class):
        config_service_class.return_value.get_config.return_value = {
            'saa_collector': {'tushare_api': {'token': 'token', 'rate_limit': 10}}
        }
        config_service_class.return_value.get_db_config.return_value = {'host': 'db'}
        pro = Mock()
        pro.query.side_effect = [
            pd.DataFrame([{'ts_code': '000906.SH', 'name': '中证800'}]),
            pd.DataFrame([
                {
                    'ts_code': '000906.SH',
                    'trade_date': '20260529',
                    'open': 100.1,
                    'high': 101.2,
                    'low': 99.3,
                    'close': 100.8,
                    'pre_close': 99.9,
                    'change': 0.9,
                    'pct_chg': 0.901,
                    'vol': 12345.0,
                    'amount': 67890.0,
                }
            ]),
        ]
        get_client.return_value = pro
        connection = Mock()
        connect.return_value = connection

        service = IndexQuoteService()
        service.collect(['000906.XSHG'], date(2026, 5, 29), date(2026, 5, 29))

        self.assertEqual(pro.query.call_args_list[0].args[0], 'index_basic')
        self.assertEqual(pro.query.call_args_list[1].args[0], 'index_daily')
        self.assertEqual(pro.query.call_args_list[1].kwargs['ts_code'], '000906.SH')
        db_class.return_value.to_sql.assert_called_once_with(
            [
                {
                    'code': '000906',
                    'date': date(2026, 5, 29),
                    'name': '中证800',
                    'open_price': 100.1,
                    'high_price': 101.2,
                    'low_price': 99.3,
                    'close_price': 100.8,
                    'turnover_volume': 12345.0,
                    'turnover_value': 67890.0,
                    'change_of': 0.9,
                    'change_pct': 0.901,
                    'prev_close_price': 99.9,
                },
            ],
            connection,
            'saa_index_quotes',
            ['code', 'date'],
        )
        connection.close.assert_called_once()
