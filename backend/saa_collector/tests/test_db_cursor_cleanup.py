from unittest import TestCase
from unittest.mock import MagicMock, patch

from saa_collector.services.common import progress as progress_module
from saa_collector.services.impl.tushare import basic_stock_service as basic_stock_module
from saa_collector.services.impl.tushare.basic_stock_service import BasicStockService


class CursorCleanupTest(TestCase):
    def test_tushare_get_symbols_from_db_closes_cursor_and_connection(self):
        service = BasicStockService.__new__(BasicStockService)
        service.db_config = {}
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchall.return_value = [('000002',), ('000001',)]

        with patch.object(basic_stock_module.mysql.connector, 'connect', return_value=connection):
            symbols = service.get_symbols_from_db()

        self.assertEqual(symbols, ['000001', '000002'])
        cursor.close.assert_called_once()
        connection.close.assert_called_once()

    def test_progress_load_listing_times_closes_cursor_and_connection(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchall.return_value = [('000001', '19910403')]

        with patch.object(progress_module, 'ConfigService') as config_service_class, \
                patch.object(progress_module.mysql.connector, 'connect', return_value=connection):
            config_service_class.return_value.get_db_config.return_value = {}

            listing_times = progress_module.load_listing_times(['000001'])

        self.assertEqual(listing_times, {'000001': '19910403'})
        cursor.close.assert_called_once()
        connection.close.assert_called_once()
