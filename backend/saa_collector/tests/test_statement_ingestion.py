from datetime import date
from unittest import TestCase
from unittest.mock import MagicMock, patch

from saa_collector.services.common.financial_statement_contract import financial_fields
from saa_collector.services.common.statement_ingestion import save_version_bundle, version_ingestion_enabled


class StatementIngestionTest(TestCase):
    def setUp(self):
        self.locks = patch('saa_collector.services.common.statement_ingestion.statement_locks')
        self.locks.start()
        self.addCleanup(self.locks.stop)

    def bundle(self):
        result = {}
        for suffix in ('balance_sheet', 'income_statement', 'cash_flow_statement'):
            table = 'saa_raw_' + suffix
            row = dict.fromkeys(financial_fields(table), None)
            row.update(symbol='600036', report_date=date(2023, 12, 31),
                       disclosure_date=date(2024, 3, 29), provider='tushare')
            result[table] = [row]
        return result

    def test_activation_is_explicit_boolean(self):
        self.assertFalse(version_ingestion_enabled({}))
        with self.assertRaises(ValueError):
            version_ingestion_enabled({'saa_collector': {'statement_versioning': {'enabled': 'false'}}})

    @patch('saa_collector.services.common.statement_ingestion.mysql.connector.connect')
    def test_invalid_bundle_never_connects(self, connect):
        bundle = self.bundle()
        bundle['saa_raw_income_statement'][0].pop('net_profit')
        with self.assertRaises(ValueError):
            save_version_bundle({}, bundle)
        connect.assert_not_called()

    @patch('saa_collector.services.common.statement_ingestion.write_versions')
    @patch('saa_collector.services.common.statement_ingestion.mysql.connector.connect')
    def test_one_commit_for_three_tables(self, connect, writer):
        connection = connect.return_value
        writer.return_value = [{'created': True, 'id': 1}]
        save_version_bundle({}, self.bundle())
        self.assertEqual(writer.call_count, 3)
        connection.start_transaction.assert_called_once_with()
        connection.commit.assert_called_once_with()
        connection.rollback.assert_not_called()
        connection.close.assert_called_once_with()

    @patch('saa_collector.services.common.statement_ingestion.write_versions')
    @patch('saa_collector.services.common.statement_ingestion.mysql.connector.connect')
    def test_later_table_failure_rolls_back_bundle_and_closes(self, connect, writer):
        writer.side_effect = [[{'created': True, 'id': 1}], RuntimeError('conflict')]
        with self.assertRaises(RuntimeError):
            save_version_bundle({}, self.bundle())
        connect.return_value.commit.assert_not_called()
        connect.return_value.rollback.assert_called_once_with()
        connect.return_value.close.assert_called_once_with()
