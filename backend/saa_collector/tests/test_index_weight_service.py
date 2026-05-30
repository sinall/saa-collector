from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
from django.test import SimpleTestCase

from saa_collector.services.common.index_weight_service import IndexWeightService


class IndexWeightServiceTest(SimpleTestCase):
    @patch('saa_collector.services.common.index_weight_service.ConfigService')
    @patch('saa_collector.services.common.index_weight_service.get_tushare_client')
    @patch('saa_collector.services.common.index_weight_service.mysql.connector.connect')
    @patch('saa_collector.services.common.index_weight_service.DB')
    def test_collect_saves_index_weights_with_stock_names(self, db_class, connect, get_client, config_service_class):
        config_service_class.return_value.get_config.return_value = {
            'saa_collector': {'tushare_api': {'token': 'token', 'rate_limit': 10}}
        }
        config_service_class.return_value.get_db_config.return_value = {'host': 'db'}
        pro = Mock()
        pro.query.return_value = pd.DataFrame([
            {
                'index_code': '000906.SH',
                'con_code': '000001.SZ',
                'trade_date': '20260529',
                'weight': 0.76,
            },
            {
                'index_code': '000906.SH',
                'con_code': '600000.SH',
                'trade_date': '20260529',
                'weight': 1.23,
            },
        ])
        get_client.return_value = pro
        cursor = Mock()
        cursor.fetchall.return_value = [
            ('000001', '平安银行'),
            ('600000', '浦发银行'),
        ]
        connection = Mock()
        connection.cursor.return_value = cursor
        connect.return_value = connection

        service = IndexWeightService()
        with self.assertLogs(level='INFO') as logs:
            service.collect(['000906.XSHG'], date(2026, 5, 29), date(2026, 5, 29))

        self.assertEqual(pro.query.call_args.args[0], 'index_weight')
        self.assertEqual(pro.query.call_args.kwargs['index_code'], '000906.SH')
        self.assertIn(
            "Saved 2 records to saa_index_weights; sample={'index': '000906.XSHG', "
            "'date': '2026-05-29', 'code': '000001', 'display_name': '平安银行', 'weight': 0.76}",
            logs.output[0],
        )
        db_class.return_value.to_sql.assert_called_once_with(
            [
                {
                    'index': '000906.XSHG',
                    'date': date(2026, 5, 29),
                    'code': '000001',
                    'display_name': '平安银行',
                    'weight': 0.76,
                },
                {
                    'index': '000906.XSHG',
                    'date': date(2026, 5, 29),
                    'code': '600000',
                    'display_name': '浦发银行',
                    'weight': 1.23,
                },
            ],
            connection,
            'saa_index_weights',
            ['index', 'date', 'code'],
        )
        cursor.close.assert_called_once()
        connection.close.assert_called_once()
