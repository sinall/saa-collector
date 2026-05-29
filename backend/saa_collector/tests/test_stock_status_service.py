from datetime import date
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from saa_collector.services.common.stock_status_service import StockStatusService


class StockStatusServiceTest(SimpleTestCase):
    @patch('saa_collector.services.common.stock_status_service.ConfigService')
    @patch('saa_collector.services.common.stock_status_service.mysql.connector.connect')
    @patch('saa_collector.services.common.stock_status_service.DB')
    def test_collect_saves_current_st_snapshot_from_stocks(self, db_class, connect, config_service_class):
        config_service_class.return_value.get_db_config.return_value = {'host': 'db'}
        cursor = Mock()
        cursor.fetchall.return_value = [
            ('000001', '平安银行'),
            ('000005', 'ST星源'),
            ('000007', '*ST全新'),
            ('000008', '＊ＳＴ测试'),
        ]
        connection = Mock()
        connection.cursor.return_value = cursor
        connect.return_value = connection

        service = StockStatusService()
        service.collect(date(2026, 5, 29))

        db_class.return_value.to_sql.assert_called_once_with(
            [
                {'code': '000001', 'date': date(2026, 5, 29), 'is_st': 0},
                {'code': '000005', 'date': date(2026, 5, 29), 'is_st': 1},
                {'code': '000007', 'date': date(2026, 5, 29), 'is_st': 1},
                {'code': '000008', 'date': date(2026, 5, 29), 'is_st': 1},
            ],
            connection,
            'saa_extras',
            ['code', 'date'],
        )
        cursor.close.assert_called_once()
        connection.close.assert_called_once()
