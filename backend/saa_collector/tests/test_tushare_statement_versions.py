from datetime import date
from decimal import Decimal
from itertools import permutations
from unittest import TestCase
from unittest.mock import MagicMock, patch
from pathlib import Path

import pandas as pd

from saa_collector.services.common.financial_statement_contract import financial_fields
from saa_collector.services.common.statement_source_adapter import tushare_snapshots


TABLE = 'saa_raw_income_statement'


class TushareStatementVersionsTest(TestCase):
    def setUp(self):
        self.mapping = pd.DataFrame([
            dict(Field=field, TushareField=field, TushareUnit=1)
            for field in financial_fields(TABLE)
        ])
        self.raw = dict.fromkeys(financial_fields(TABLE), None)
        self.raw.update(ts_code='600036.SH', end_date='20231231',
                        ann_date='20240329', f_ann_date='20240329',
                        report_type='1', net_profit=123.45)

    def convert(self, rows):
        return tushare_snapshots(TABLE, rows, self.mapping)

    def test_original_and_revision_both_survive_and_are_ordered(self):
        original = dict(self.raw, report_type='5')
        revision = dict(self.raw, report_type='4', f_ann_date='20250328', net_profit=130)
        rows = self.convert([revision, original, dict(original)])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['disclosure_date'], date(2024, 3, 29))
        self.assertEqual(rows[1]['net_profit'], Decimal('130.00'))
        self.assertEqual(rows[0]['source_metadata']['report_type'], '5')
        self.assertEqual(self.raw['net_profit'], 123.45)

    def test_same_day_conflict_is_not_arbitrarily_deduplicated(self):
        with self.assertRaisesRegex(ValueError, 'conflict.*net_profit') as caught:
            self.convert([self.raw, dict(self.raw, net_profit=100)])
        issue = caught.exception.issue
        self.assertEqual(issue['symbol'], '600036')
        self.assertFalse(issue['differences']['net_profit']['existing_present'])
        self.assertEqual({v['value'] for v in issue['differences']['net_profit']['candidates']},
                         {'100.00', '123.45'})

    def test_missing_mapped_field_is_not_implicit_null(self):
        del self.raw['net_profit']
        with self.assertRaisesRegex(ValueError, 'Missing source field'):
            self.convert([self.raw])

    def test_same_day_updated_snapshot_wins_independent_of_order(self):
        old = dict(self.raw, update_flag='0')
        newer = dict(self.raw, update_flag='1', net_profit=None)
        for rows in ([old, newer], [newer, old]):
            result = self.convert(rows)
            self.assertEqual(len(result), 1)
            self.assertIsNone(result[0]['net_profit'])
            self.assertEqual(result[0]['source_metadata']['update_flag'], '1')

    def test_conflicting_updated_snapshots_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'conflict'):
            self.convert([dict(self.raw, update_flag='1'),
                          dict(self.raw, update_flag='1', net_profit=999)])

    def test_report_type_priority_is_order_independent_and_keeps_whole_snapshot(self):
        latest = dict(self.raw, report_type='1', update_flag='0', net_profit=None)
        adjusted = dict(self.raw, report_type='4', update_flag='1', net_profit=200)
        original = dict(self.raw, report_type='5', update_flag='1', net_profit=300)
        for records in permutations([latest, adjusted, original]):
            with self.subTest(order=[r['report_type'] for r in records]):
                row = self.convert(records)[0]
                self.assertIsNone(row['net_profit'])
                self.assertEqual(row['source_metadata']['report_type'], '1')
                self.assertEqual(row['source_metadata']['update_flag'], '0')

    def test_adjusted_precedes_original_when_latest_is_absent(self):
        adjusted = dict(self.raw, report_type='4', update_flag='0', net_profit=200)
        original = dict(self.raw, report_type='5', update_flag='1', net_profit=300)
        for records in ([adjusted, original], [original, adjusted]):
            row = self.convert(records)[0]
            self.assertEqual(row['net_profit'], Decimal('200.00'))
            self.assertEqual(row['source_metadata']['report_type'], '4')

    def test_update_flag_resolves_within_selected_type_only(self):
        records = [dict(self.raw, report_type='1', update_flag='0', net_profit=10),
                   dict(self.raw, report_type='1', update_flag='1', net_profit=20),
                   dict(self.raw, report_type='4', update_flag='1', net_profit=30)]
        for ordered in permutations(records):
            self.assertEqual(self.convert(ordered)[0]['net_profit'], Decimal('20.00'))

    def test_same_rank_adjusted_sign_conflict_is_still_rejected(self):
        records = [dict(self.raw, report_type='4', update_flag='1', net_profit=value)
                   for value in (-172014721.27, 172014721.27)]
        for ordered in (records, records[::-1]):
            with self.assertRaisesRegex(ValueError, 'conflict'):
                self.convert(ordered)

    def test_different_disclosure_dates_are_not_compared_by_report_type(self):
        records = [dict(self.raw, report_type='1', net_profit=10),
                   dict(self.raw, report_type='4', f_ann_date='20250328', net_profit=20),
                   dict(self.raw, report_type='5', f_ann_date='20260328', net_profit=30)]
        rows = self.convert(records)
        self.assertEqual([r['net_profit'] for r in rows], list(map(Decimal, ('10', '20', '30'))))

    def test_lower_priority_resolution_is_logged_without_financial_values(self):
        with self.assertLogs('saa_collector.services.common.statement_source_adapter', level='INFO') as logs:
            self.convert([self.raw, dict(self.raw, report_type='4', net_profit=987654321)])
        output = '\n'.join(logs.output)
        self.assertIn('selected_report_type=1', output)
        self.assertIn('600036', output)
        self.assertNotIn('987654321', output)

    def test_nan_disclosure_falls_back_but_bad_date_does_not(self):
        rows = self.convert([dict(self.raw, f_ann_date=float('nan'))])
        self.assertEqual(rows[0]['disclosure_date'], date(2024, 3, 29))
        for changes in ({'f_ann_date': 'invalid'},
                        {'ann_date': None, 'f_ann_date': None},
                        {'end_date': '20231031'},
                        {'f_ann_date': '20230101'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.convert([dict(self.raw, **changes)])

    def test_unsupported_scope_and_duplicate_mapping_rejected(self):
        for report_type in ('2', '6', '', None, 'unexpected'):
            with self.subTest(report_type=report_type), self.assertRaises(ValueError):
                self.convert([dict(self.raw, report_type=report_type)])
        self.mapping = pd.concat([self.mapping, self.mapping.iloc[:1]])
        with self.assertRaisesRegex(ValueError, 'Duplicate mapping'):
            self.convert([self.raw])

    def test_explicit_sdk_null_and_decimal_quantization(self):
        rows = self.convert([dict(self.raw, net_profit=123.455,
                                  operating_cost=float('nan'))])
        self.assertEqual(rows[0]['net_profit'], Decimal('123.46'))
        self.assertIsNone(rows[0]['operating_cost'])
        with self.assertRaises(ValueError):
            self.convert([dict(self.raw, net_profit=float('inf'))])

    def test_unmapped_fields_require_explicit_coverage_contract(self):
        self.mapping.loc[self.mapping.Field == 'net_profit', 'TushareField'] = None
        with self.assertRaisesRegex(ValueError, 'Unreviewed unmapped'):
            self.convert([self.raw])

    def test_frozen_mapping_can_declare_known_unsupported_fields(self):
        self.mapping.loc[self.mapping.Field == 'subsidy_income', 'TushareField'] = None
        rows = self.convert([self.raw])
        self.assertIsNone(rows[0]['subsidy_income'])
        self.assertEqual(rows[0]['source_metadata']['omitted_fields'], ['subsidy_income'])
        self.assertEqual(rows[0]['provider'], 'tushare')

    def test_all_three_actual_xls_mappings_have_explicit_coverage(self):
        from saa_collector.services.common.statement_source_adapter import (
            TUSHARE_RESOURCES,
        )
        book = pd.read_excel(Path(__file__).parents[1] / 'config/table-config.xls', sheet_name=None)
        for table in TUSHARE_RESOURCES:
            with self.subTest(table=table):
                mapping = book[table]
                raw = dict(self.raw)
                for source in mapping['TushareField'].dropna():
                    raw.setdefault(source.strip(), None)
                rows = tushare_snapshots(table, [raw], mapping)
                self.assertEqual(set(financial_fields(table)) - rows[0].keys(), set())

    def test_xls_income_mappings_request_and_preserve_supported_values(self):
        book = Path(__file__).parents[1] / 'config/table-config.xls'
        mapping = pd.read_excel(book, sheet_name=TABLE)
        original = mapping.copy(deep=True)
        service = TushareVersionServiceTest().service()
        service.config_service.get_table_config.return_value = mapping
        requested = service.build_fields(TABLE, 'income').split(',')
        additions = {'basic_earnings_per_share': 'basic_eps',
                     'diluted_earnings_per_share': 'diluted_eps',
                     'other_comprehensive_income': 'oth_compr_income',
                     'total_comprehensive_income': 't_compr_income'}
        for field, source in additions.items():
            self.assertEqual(mapping.set_index('Field').loc[field, 'TushareField'], source)
        self.assertTrue(set(additions.values()).issubset(requested))
        raw = dict.fromkeys(requested, None)
        raw.update(ts_code='600036.SH', end_date='20231231',
                   ann_date='20240329', f_ann_date='20240329', report_type='1')
        raw.update(dict.fromkeys(additions.values(), 12.34))
        row = tushare_snapshots(TABLE, [raw], mapping)[0]
        for field in additions:
            self.assertEqual(row[field], Decimal('12.34'))
        pd.testing.assert_frame_equal(mapping, original)
        service.config = {}
        self.assertTrue(set(additions.values()).issubset(service.build_fields(TABLE, 'income').split(',')))


class TushareVersionServiceTest(TestCase):
    def test_full_page_is_followed_until_empty_page(self):
        service = self.service()
        first = pd.DataFrame([dict(ts_code='600036.SH', report_type='1', seq=i)
                              for i in range(100)])
        service.pro.query.side_effect = [first, first.assign(seq=range(100, 200)), pd.DataFrame()]
        rows = service.query_record('balancesheet', '600036', report_type='1')
        self.assertEqual(len(rows), 200)
        self.assertEqual([c.kwargs['offset'] for c in service.pro.query.call_args_list], [0, 100, 200])
        self.assertTrue(all(c.kwargs['limit'] == 100 for c in service.pro.query.call_args_list))

    def test_repeated_full_page_fails_instead_of_looping(self):
        service = self.service()
        service.pro.query.return_value = pd.DataFrame([
            dict(ts_code='600036.SH', report_type='1', seq=i) for i in range(100)])
        with self.assertRaisesRegex(ValueError, 'pagination'):
            service.query_record('balancesheet', '600036', report_type='1')
        self.assertEqual(service.pro.query.call_count, 2)

    def test_second_page_failure_does_not_return_partial_history(self):
        service = self.service()
        service.pro.query.side_effect = [pd.DataFrame([
            dict(ts_code='600036.SH', report_type='1', seq=i) for i in range(100)]),
            RuntimeError('upstream unavailable')]
        with self.assertRaisesRegex(RuntimeError, 'upstream'):
            service.query_record('balancesheet', '600036', report_type='1')

    def service(self):
        from saa_collector.services.impl.tushare.statement_service import StatementServiceImpl
        service = object.__new__(StatementServiceImpl)
        service.config = {'saa_collector': {'statement_versioning': {'enabled': True}}}
        service.pro = MagicMock()
        service._logger = MagicMock()
        service.config_service = MagicMock()
        service.db_config = {}
        return service

    def test_query_requests_each_consolidated_version_type_without_period_dedup(self):
        service = self.service()
        service.pro.query.side_effect = [pd.DataFrame([dict(ts_code='600036.SH',
            end_date='20231231', f_ann_date=day, report_type=kind, update_flag='1')])
            for day, kind in [('20240329', '1'), ('20250328', '4'), ('20240329', '5')]]
        rows = service.query_record('income', '600036', fields='ts_code,end_date')
        self.assertEqual(len(rows), 3)
        self.assertEqual([c.kwargs['report_type'] for c in service.pro.query.call_args_list], ['1', '4', '5'])

    def test_version_request_failure_is_not_converted_into_successful_empty_result(self):
        service = self.service()
        service.query_record = MagicMock(side_effect=RuntimeError('source unavailable'))
        with self.assertRaisesRegex(RuntimeError, 'source unavailable'):
            list(service.iter_symbol_records('income', ['600036']))

    def test_enabled_save_uses_version_writer_not_legacy_upsert(self):
        service = self.service()
        service.save_records = MagicMock()
        with patch('saa_collector.services.impl.tushare.statement_service.save_version_bundle') as save:
            service.save_statements([{'symbol': '600036'}], TABLE)
            save.assert_called_once_with({}, {TABLE: [{'symbol': '600036'}]})
        service.save_records.assert_not_called()

    def test_version_response_must_match_requested_symbol_and_type(self):
        for changes in ({'ts_code': '600000.SH'}, {'report_type': '4'}):
            service = self.service()
            row = dict(ts_code='600036.SH', report_type='1')
            row.update(changes)
            service.pro.query.return_value = pd.DataFrame([row])
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'scope'):
                service.query_record('income', '600036', report_type='1')

    def test_collect_continues_other_symbols_but_reports_partial_failure(self):
        service = self.service()
        service.build_symbols = MagicMock(return_value=['600036', '600000'])
        service._collect_one = MagicMock(side_effect=[ValueError('conflict'), None])
        with patch('saa_collector.services.impl.tushare.statement_service.ProgressLogger'):
            with self.assertRaisesRegex(RuntimeError, '600036'):
                service.collect(['600036', '600000'])
        self.assertEqual(service._collect_one.call_count, 2)

    def test_produce_without_failure_callback_cannot_silently_succeed(self):
        service = self.service()
        service.build_symbols = MagicMock(return_value=['600036'])
        service._produce_one = MagicMock(side_effect=ValueError('conflict'))
        with patch('saa_collector.services.impl.tushare.statement_service.ProgressLogger'):
            with self.assertRaisesRegex(RuntimeError, '600036'):
                service.produce(['600036'])

    def test_produce_failure_callback_remains_owner_of_job_failure(self):
        service = self.service()
        service.build_symbols = MagicMock(return_value=['600036'])
        service._produce_one = MagicMock(side_effect=ValueError('conflict'))
        failed, success, after = MagicMock(), MagicMock(), MagicMock()
        with patch('saa_collector.services.impl.tushare.statement_service.ProgressLogger'):
            service.produce(['600036'], on_symbol_failure=failed,
                            on_symbol_success=success, after_symbol=after)
        failed.assert_called_once_with('600036')
        success.assert_not_called()
        after.assert_called_once_with('600036')

    def test_issue_persistence_failure_is_not_swallowed(self):
        service = self.service()
        service.build_symbols = MagicMock(return_value=['600036'])
        service._produce_one = MagicMock(side_effect=ValueError('secret upstream response'))
        issue_sink = MagicMock(side_effect=RuntimeError('cannot persist'))
        with patch('saa_collector.services.impl.tushare.statement_service.ProgressLogger'):
            with self.assertRaisesRegex(RuntimeError, 'cannot persist'):
                service.produce(['600036'], on_symbol_issue=issue_sink)
        self.assertNotIn('secret', str(issue_sink.call_args))
