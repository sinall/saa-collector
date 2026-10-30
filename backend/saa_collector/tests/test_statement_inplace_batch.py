import unittest
from unittest.mock import Mock

from saa_collector.services.common.statement_inplace_migration import _write_hash_batch
from saa_collector.services.common.statement_shadow_copy import _pages


class InplaceHashBatchTest(unittest.TestCase):
    def test_page_uses_explicit_index_range(self):
        from datetime import date
        row = {'symbol': '600036', 'report_date': date(2020, 12, 31)}
        cursor = Mock()
        cursor.fetchall.side_effect = [[row], []]
        self.assertEqual(list(_pages(cursor, 'saa_raw_income_statement', 1)), [[row]])
        sql, params = cursor.execute.call_args.args
        self.assertIn('symbol > %s OR (symbol=%s AND report_date > %s)', sql)
        self.assertEqual(params, ('600036', '600036', date(2020, 12, 31), 1))

    def test_one_parameterized_update_per_batch(self):
        cursor = Mock(rowcount=2)
        _write_hash_batch(cursor, 'saa_raw_income_statement', [('a' * 64, 7), ('b' * 64, 8)])
        cursor.execute.assert_called_once()
        sql, params = cursor.execute.call_args.args
        self.assertIn('CASE id WHEN %s THEN %s WHEN %s THEN %s END', sql)
        self.assertIn('content_hash IS NULL', sql)
        self.assertNotIn('a' * 64, sql)
        self.assertEqual(params, (7, 'a' * 64, 8, 'b' * 64, 7, 8))
        cursor.executemany.assert_not_called()

    def test_count_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'update count'):
            _write_hash_batch(Mock(rowcount=0), 'saa_raw_income_statement', [('a' * 64, 7)])

    def test_empty_batch_and_unknown_table(self):
        cursor = Mock()
        _write_hash_batch(cursor, 'saa_raw_income_statement', [])
        cursor.execute.assert_not_called()
        with self.assertRaises(KeyError):
            _write_hash_batch(cursor, 'unreviewed_table', [('a' * 64, 7)])
