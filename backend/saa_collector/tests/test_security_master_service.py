from unittest.mock import MagicMock, patch

from django.test import TestCase

from saa_collector.services.common.security_master_service import SecurityMasterRefreshService


class SecurityMasterRefreshServiceTest(TestCase):
    def test_refresh_from_stocks_uses_existing_connection_and_keeps_it_open(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.rowcount = 3

        affected_rows = SecurityMasterRefreshService().refresh_from_stocks(connection)

        self.assertEqual(affected_rows, 3)
        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args.args[0]
        self.assertIn('INSERT INTO saa_securities', sql)
        self.assertIn('FROM saa_stocks s', sql)
        self.assertIn("s.type = 'STOCK'", sql)
        self.assertIn("s.market = 'A'", sql)
        self.assertIn("name = COALESCE(NULLIF(name, ''), VALUES(name))", sql)
        connection.commit.assert_called_once()
        cursor.close.assert_called_once()
        connection.close.assert_not_called()

    @patch('saa_collector.services.common.security_master_service.mysql.connector.connect')
    def test_refresh_from_stocks_closes_owned_connection(self, connect):
        connection = connect.return_value
        cursor = connection.cursor.return_value
        cursor.rowcount = 1

        affected_rows = SecurityMasterRefreshService().refresh_from_stocks()

        self.assertEqual(affected_rows, 1)
        connect.assert_called_once()
        connection.commit.assert_called_once()
        cursor.close.assert_called_once()
        connection.close.assert_called_once()
