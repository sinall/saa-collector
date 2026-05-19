# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch

from saa_collector.services.common import statement_maintain_service as module
from saa_collector.services.common.statement_maintain_service import StatementMaintainService


class StatementMaintainServiceTest(unittest.TestCase):
    def build_service(self):
        with patch.object(module, 'ConfigService') as config_service_class:
            config_service_class.return_value.get_db_config.return_value = {}
            return StatementMaintainService()

    def test_refresh_financial_report_cache_closes_connection(self):
        service = self.build_service()
        connection = MagicMock()
        cursor = connection.cursor.return_value

        with patch.object(module.mysql.connector, 'connect', return_value=connection):
            service.refresh_financial_report_cache('000001')

        cursor.close.assert_called_once()
        connection.close.assert_called_once()

    def test_refresh_ttm_report_cache_closes_connection(self):
        service = self.build_service()
        service.get_fields = MagicMock(return_value=[])
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchall.return_value = []

        with patch.object(module.mysql.connector, 'connect', return_value=connection):
            service.refresh_ttm_report_cache('000001')

        cursor.close.assert_called_once()
        connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
