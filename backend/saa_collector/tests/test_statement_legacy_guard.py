import unittest
from unittest.mock import MagicMock

from saa_collector.services.common.statement_legacy_guard import assert_legacy_write_allowed


class LegacyStatementGuardTest(unittest.TestCase):
    def test_provider_legacy_helpers_cannot_bypass_guard(self):
        from importlib import import_module
        for provider in ('tushare', 'akshare', 'cninfo'):
            with self.subTest(provider=provider):
                cls = import_module('saa_collector.services.impl.' + provider +
                                    '.basic_stock_service').BasicStockService
                service = cls.__new__(cls)
                connection = MagicMock()
                cursor = connection.cursor.return_value
                cursor.fetchall.return_value = [('id',)]
                with self.assertRaisesRegex(ValueError, 'version'):
                    service.to_sql([dict(symbol='A')], connection,
                                   'saa_raw_income_statement', ['symbol', 'report_date'])
                connection.commit.assert_not_called()
                cursor.close.assert_called_once()

    def test_other_tables_do_not_query_schema(self):
        cursor = MagicMock()
        assert_legacy_write_allowed(cursor, 'saa_prices')
        cursor.execute.assert_not_called()

    def test_legacy_primary_key_is_allowed(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [('symbol',), ('report_date',), ('disclosure_date',)],
            [('t', 0, 'PRIMARY', 2, 'report_date'),
             ('t', 0, 'PRIMARY', 1, 'symbol')],
        ]
        assert_legacy_write_allowed(cursor, 'saa_raw_income_statement')

    def test_version_or_partial_migration_rejects_legacy_write(self):
        for marker in ('id', 'provider', 'source_metadata', 'content_hash'):
            cursor = MagicMock()
            cursor.fetchall.return_value = [('symbol',), ('report_date',), (marker,)]
            with self.assertRaisesRegex(ValueError, 'version'):
                assert_legacy_write_allowed(cursor, 'saa_raw_income_statement')

    def test_unknown_primary_key_rejects_write(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [[('symbol',), ('report_date',)], []]
        with self.assertRaises(ValueError):
            assert_legacy_write_allowed(cursor, 'saa_raw_income_statement')

    def test_generic_upsert_is_blocked_before_dml(self):
        from saa_collector.utils.db import DB
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchall.return_value = [('id',), ('symbol',), ('report_date',)]
        with self.assertRaisesRegex(ValueError, 'version'):
            DB().to_sql([dict(symbol='A', report_date='2023-12-31')], connection,
                        'saa_raw_income_statement', ['symbol', 'report_date'])
        self.assertFalse(any('INSERT' in str(call) for call in cursor.execute.call_args_list))
        connection.commit.assert_not_called()
        cursor.close.assert_called_once()
