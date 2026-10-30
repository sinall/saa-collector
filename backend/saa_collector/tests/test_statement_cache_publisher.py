from datetime import date
from unittest import TestCase
from unittest.mock import MagicMock, patch

from saa_collector.services.common.statement_cache_publisher import (
    CACHE_COLUMNS, build_cache_candidates, publish_statement_caches,
)
from saa_collector.services.common.statement_maintain_service import StatementMaintainService


class StatementCachePublisherTest(TestCase):
    def row(self, period=date(2023, 12, 31), value=100):
        row = dict.fromkeys(CACHE_COLUMNS)
        row.update(symbol='600036', report_date=period,
                   disclosure_date=date(2024, 3, 29), net_profit=value)
        return row

    def test_candidates_use_same_snapshot_dividend_and_ttm(self):
        rows = [self.row(), self.row(date(2023, 9, 30), 70), self.row(date(2024, 9, 30), 90)]
        service = object.__new__(StatementMaintainService)
        integrated, ttm = build_cache_candidates(
            service, '600036', rows, [{'year': 2024, 'dividend': 50}], [], date(2020, 1, 1))
        self.assertEqual(ttm[0]['net_profit'], 120)
        self.assertEqual(ttm[0]['dividend'], 50)
        self.assertIsNone(rows[-1]['dividend'])
        self.assertEqual(len(integrated), 3)

    def test_duplicate_scope_missing_dependency_or_withdrawal_refuses_publication(self):
        service = object.__new__(StatementMaintainService)
        cases = [([self.row(), self.row()], [], []),
                 ([self.row(date(2024, 9, 30))], [], []),
                 ([self.row()], [], [{'report_date': date(2022, 12, 31)}]),
                 ([self.row()], [{'year': 2023, 'dividend': 1}, {'year': 2023, 'dividend': 2}], []),
                 ([], [], [])]
        for rows, dividends, existing in cases:
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                build_cache_candidates(service, '600036', rows, dividends, existing, date(2020, 1, 1))

    def test_exchange_uses_existing_two_character_cache_contract(self):
        service = object.__new__(StatementMaintainService)
        for source, expected in [('SZSE', 'SZ'), ('SSE', 'SS'), ('SH', 'SH'),
                                 ('SZ', 'SZ'), ('BJ', 'BJ'), ('HK', 'HK'), (None, None)]:
            with self.subTest(exchange=source):
                row = self.row()
                row['exchange'] = source
                integrated, ttm = build_cache_candidates(
                    service, '600036', [row], [], [], date(2020, 1, 1))
                self.assertEqual(integrated[0]['exchange'], expected)
                self.assertEqual(ttm[0]['exchange'], expected)
                self.assertEqual(row['exchange'], source)
        row = self.row()
        row['exchange'] = 'UNKNOWN_EXCHANGE'
        with self.assertRaisesRegex(ValueError, 'Unknown cache exchange'):
            build_cache_candidates(service, '600036', [row], [], [], date(2020, 1, 1))

    @patch('saa_collector.services.common.statement_cache_publisher.statement_locks')
    @patch('saa_collector.services.common.statement_cache_publisher.DB')
    def test_second_cache_write_failure_rolls_back_first(self, db, locks):
        cnx = MagicMock()
        cnx.autocommit = False
        cnx.in_transaction = False
        cursor = cnx.cursor.return_value
        cursor.fetchall.side_effect = [[self.row()], [], []]
        cursor.fetchone.return_value = {'cutoff': date(2020, 1, 1)}
        db.return_value.to_sql.side_effect = [None, RuntimeError('TTM write failure')]
        with self.assertRaisesRegex(RuntimeError, 'TTM write failure'):
            publish_statement_caches(cnx, object.__new__(StatementMaintainService), '600036')
        cnx.commit.assert_not_called()
        cnx.rollback.assert_called_once()
        self.assertEqual(db.return_value.to_sql.call_count, 2)
        self.assertTrue(all(call.kwargs['commit'] is False for call in db.return_value.to_sql.call_args_list))
