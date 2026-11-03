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

    def test_historical_quarters_read_previous_calendar_year_through_target(self):
        for month, day in [(3, 31), (6, 30), (9, 30)]:
            with self.subTest(month=month):
                target = date(2015, month, day)
                rows = [self.row(date(2013, 12, 31), 900),
                        self.row(date(2014, month, day), 60),
                        self.row(date(2014, 12, 31), 100), self.row(target, 80)]
                service = object.__new__(StatementMaintainService)
                original = service.build_ttm_candidates
                service.build_ttm_candidates = MagicMock(wraps=original)
                integrated, ttm = build_cache_candidates(service, '600036', rows, [], [])
                self.assertEqual(ttm[0]['net_profit'], 120)
                self.assertEqual(ttm[0]['report_date'], target)
                received = service.build_ttm_candidates.call_args.args[0]
                self.assertEqual({r['report_date'] for r in received},
                    {date(2014, month, day), date(2014, 12, 31), target})
                self.assertEqual(len(integrated), 4)

    def test_historical_annual_report_needs_no_recent_wall_clock_input(self):
        service = object.__new__(StatementMaintainService)
        _, ttm = build_cache_candidates(service, '600036', [self.row(date(2016, 12, 31), 80)], [], [])
        self.assertEqual(ttm[0]['net_profit'], 80)

    def test_absent_old_cache_period_does_not_block_new_periods(self):
        service = object.__new__(StatementMaintainService)
        integrated, ttm = build_cache_candidates(service, '600036', [self.row()], [],
                                                [{'report_date': date(2006, 12, 31)}])
        self.assertEqual(len(integrated), 1)
        self.assertEqual(ttm[0]['net_profit'], 100)

    def test_nonquarter_does_not_become_ttm_target(self):
        service = object.__new__(StatementMaintainService)
        rows = [self.row(date(2022, 9, 30), 60), self.row(date(2022, 12, 31), 100),
                self.row(date(2023, 9, 30), 80), self.row(date(2023, 10, 31), 900)]
        integrated, ttm = build_cache_candidates(service, '600036', rows, [], [])
        self.assertEqual(len(integrated), 4)
        self.assertEqual(ttm[0]['report_date'], date(2023, 9, 30))
        self.assertEqual(ttm[0]['net_profit'], 120)

    def test_candidates_use_same_snapshot_dividend_and_ttm(self):
        rows = [self.row(), self.row(date(2023, 9, 30), 70), self.row(date(2024, 9, 30), 90)]
        service = object.__new__(StatementMaintainService)
        integrated, ttm = build_cache_candidates(
            service, '600036', rows, [{'year': 2024, 'dividend': 50}], [])
        self.assertEqual(ttm[0]['net_profit'], 120)
        self.assertEqual(ttm[0]['dividend'], 50)
        self.assertIsNone(rows[-1]['dividend'])
        self.assertEqual(len(integrated), 3)

    def test_duplicate_scope_missing_dependency_or_withdrawal_refuses_publication(self):
        service = object.__new__(StatementMaintainService)
        cases = [([self.row(), self.row()], [], []),
                 ([self.row(date(2024, 9, 30))], [], []),
                 ([self.row()], [{'year': 2023, 'dividend': 1}, {'year': 2023, 'dividend': 2}], []),
                 ([], [], [])]
        for rows, dividends, existing in cases:
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                build_cache_candidates(service, '600036', rows, dividends, existing)

    def test_exchange_uses_existing_two_character_cache_contract(self):
        service = object.__new__(StatementMaintainService)
        for source, expected in [('SZSE', 'SZ'), ('SSE', 'SS'), ('SH', 'SH'),
                                 ('SZ', 'SZ'), ('BJ', 'BJ'), ('HK', 'HK'), (None, None)]:
            with self.subTest(exchange=source):
                row = self.row()
                row['exchange'] = source
                integrated, ttm = build_cache_candidates(
                    service, '600036', [row], [], [])
                self.assertEqual(integrated[0]['exchange'], expected)
                self.assertEqual(ttm[0]['exchange'], expected)
                self.assertEqual(row['exchange'], source)
        row = self.row()
        row['exchange'] = 'UNKNOWN_EXCHANGE'
        with self.assertRaisesRegex(ValueError, 'Unknown cache exchange'):
            build_cache_candidates(service, '600036', [row], [], [])

    @patch('saa_collector.services.common.statement_cache_publisher.statement_locks')
    @patch('saa_collector.services.common.statement_cache_publisher.DB')
    def test_second_cache_write_failure_rolls_back_first(self, db, locks):
        cnx = MagicMock()
        cnx.autocommit = False
        cnx.in_transaction = False
        cursor = cnx.cursor.return_value
        cursor.fetchall.side_effect = [[self.row()], [], []]
        db.return_value.to_sql.side_effect = [None, RuntimeError('TTM write failure')]
        with self.assertRaisesRegex(RuntimeError, 'TTM write failure'):
            publish_statement_caches(cnx, object.__new__(StatementMaintainService), '600036')
        cnx.commit.assert_not_called()
        cnx.rollback.assert_called_once()
        self.assertEqual(db.return_value.to_sql.call_count, 2)
        self.assertTrue(all(call.kwargs['commit'] is False for call in db.return_value.to_sql.call_args_list))
