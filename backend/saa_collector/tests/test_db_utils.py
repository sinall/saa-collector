from unittest import TestCase
from unittest.mock import MagicMock

from saa_collector.utils.db import DB


class DBToSqlTest(TestCase):
    def test_caller_owned_transaction_is_not_committed(self):
        connection = MagicMock(in_transaction=True, autocommit=False)
        DB().to_sql([{'symbol': 'A', 'value': 1}], connection, 'cache',
                    ['symbol'], commit=False)
        connection.commit.assert_not_called()
        connection.rollback.assert_not_called()
        connection.cursor.return_value.close.assert_called_once()

    def test_caller_owned_mode_requires_an_explicit_transaction(self):
        for active, autocommit in [(False, False), (True, True)]:
            connection = MagicMock(in_transaction=active, autocommit=autocommit)
            with self.assertRaises(ValueError):
                DB().to_sql([{'symbol': 'A'}], connection, 'cache',
                            ['symbol'], commit=False)
            connection.cursor.assert_not_called()

    def test_default_mode_still_commits(self):
        connection = MagicMock()
        DB().to_sql([{'symbol': 'A'}], connection, 'cache', ['symbol'])
        connection.commit.assert_called_once()

    def test_to_sql_closes_prepared_cursor_after_success(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value

        DB().to_sql([{'symbol': '000001', 'date': '2024-12-31'}], connection, 'table', ['symbol'])

        connection.cursor.assert_called_once_with(prepared=True)
        cursor.close.assert_called_once()

    def test_to_sql_closes_prepared_cursor_after_execute_failure(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.execute.side_effect = RuntimeError('execute failed')

        with self.assertRaises(RuntimeError):
            DB().to_sql([{'symbol': '000001', 'date': '2024-12-31'}], connection, 'table', ['symbol'])

        cursor.close.assert_called_once()

    def test_to_sql_quotes_columns_for_reserved_words(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value

        DB().to_sql(
            [{'index': '000906.XSHG', 'date': '2026-05-29', 'code': '000001', 'weight': 0.76}],
            connection,
            'saa_index_weights',
            ['index', 'date', 'code'],
        )

        sql = cursor.execute.call_args.args[0]
        self.assertIn('INSERT INTO `saa_index_weights` (`index`, `date`, `code`, `weight`)', sql)
        self.assertIn('`weight` = VALUES(`weight`)', sql)

    def test_to_sql_uses_noop_update_when_all_fields_are_primary_keys(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value

        DB().to_sql(
            [{'industry_code': '801010', 'date': '2026-05-30', 'code': '000505'}],
            connection,
            'saa_industry_stocks',
            ['industry_code', 'date', 'code'],
        )

        sql = cursor.execute.call_args.args[0]
        self.assertIn('ON DUPLICATE KEY UPDATE `industry_code` = VALUES(`industry_code`)', sql)
