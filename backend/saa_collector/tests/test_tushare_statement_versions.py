from datetime import date
import json
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

    def test_unresolved_candidates_null_only_disagreements_and_emit_quality(self):
        from saa_collector.services.common.statement_source_adapter import statement_field_issues
        from saa_collector.services.common.statement_version_writer import prepare_version
        source = [dict(self.raw, net_profit=100, total_profit=200),
                  dict(self.raw, net_profit=120, total_profit=200),
                  dict(self.raw, net_profit=None, total_profit=200)]
        expected = None
        for candidates in permutations(source):
            rows = self.convert(list(candidates))
            self.assertIsNone(rows[0]['net_profit'])
            self.assertEqual(rows[0]['total_profit'], 200)
            if expected is None:
                expected = rows
            self.assertEqual(rows, expected)
            issues = statement_field_issues(TABLE, rows[0])
            self.assertEqual(issues[-1]['action'], 'STORE_NULL_CONTINUE')
            values = issues[-1]['differences']['net_profit']['candidates']
            self.assertEqual(set(values), {'100.00', '120.00', None})
            prepare_version(TABLE, rows[0])
        self.assertEqual(source[0]['net_profit'], 100)

    def test_real_300202_conflict_keeps_profit_and_degrades_associate_income(self):
        from saa_collector.services.common.statement_source_adapter import statement_field_issues
        fixture = Path(__file__).parent / 'fixtures/tushare_conflict_300202.json'
        source = json.loads(fixture.read_text())
        mapping = pd.read_excel(Path(__file__).parents[1] / 'config/table-config.xls', sheet_name=TABLE)
        out = tushare_snapshots(TABLE, source, mapping, normalize_signs=True)
        self.assertEqual(out, tushare_snapshots(TABLE, source[::-1], mapping, normalize_signs=True))
        row = out[0]
        self.assertIsNone(row['share_of_profits_in_associates_and_joint_ventures'])
        self.assertEqual(row['net_profit'], Decimal('-83984934.88'))
        audit = json.loads(row['source_metadata']['conflict_null_audit'])
        self.assertEqual(len(audit['sources']), 2)
        self.assertEqual({r['metadata']['ann_date'] for r in audit['sources']},
                         {'20260429', '20260430'})
        self.assertTrue(statement_field_issues(TABLE, row))

    def test_conflict_fallback_applies_to_all_statement_tables(self):
        from saa_collector.services.common.statement_source_adapter import statement_field_issues
        for table in ['saa_raw_balance_sheet', 'saa_raw_cash_flow_statement']:
            fields = financial_fields(table)
            mapping = pd.DataFrame([dict(Field=f, TushareField=f, TushareUnit=1) for f in fields])
            raw = dict.fromkeys(fields, None)
            raw.update(ts_code='600036.SH', end_date='20231231', f_ann_date='20240329', report_type='4')
            field = fields[0]
            out = tushare_snapshots(table, [dict(raw, **{field: 100}), dict(raw, **{field: 150})],
                                    mapping, latest_query_complete=True)
            self.assertEqual(len(out), 2)
            for row in out:
                self.assertIsNone(row[field])
                self.assertEqual(statement_field_issues(table, row)[0]['action'], 'STORE_NULL_CONTINUE')

    def test_confirmed_absence_derives_latest_without_relabelling_history(self):
        rows = [dict(self.raw, report_type='5'),
                dict(self.raw, report_type='4', net_profit=200)]
        out = tushare_snapshots(TABLE, rows, self.mapping, latest_query_complete=True)
        self.assertEqual(len(out), 3)
        latest = next(r for r in out if r['version_type'] == 'LATEST')
        self.assertEqual(latest['net_profit'], Decimal('200.00'))
        self.assertEqual(latest['source_metadata']['derived_from_type'], 'RESTATED')
        self.assertEqual(latest['source_metadata']['snapshot_origin'], 'derived_latest')
        self.assertNotIn('report_type', latest['source_metadata'])
        self.assertEqual(rows[1]['report_type'], '4')

    def test_incomplete_query_does_not_derive_latest(self):
        out = self.convert([dict(self.raw, report_type='4')])
        self.assertEqual([r['version_type'] for r in out], ['RESTATED'])

    def test_real_latest_wins_even_if_historical_disclosure_is_newer(self):
        out = tushare_snapshots(TABLE, [self.raw, dict(self.raw, report_type='4',
            f_ann_date='20250328', net_profit=200)], self.mapping, latest_query_complete=True)
        latest = [r for r in out if r['version_type'] == 'LATEST']
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]['source_metadata']['report_type'], '1')

    def test_original_and_revision_both_survive_and_are_ordered(self):
        original = dict(self.raw, report_type='5')
        revision = dict(self.raw, report_type='4', f_ann_date='20250328', net_profit=130)
        rows = self.convert([revision, original, dict(original)])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['disclosure_date'], date(2024, 3, 29))
        self.assertEqual(rows[1]['net_profit'], Decimal('130.00'))
        self.assertEqual(rows[0]['source_metadata']['report_type'], '5')
        self.assertEqual(self.raw['net_profit'], 123.45)

    def test_same_day_conflict_nullifies_instead_of_arbitrary_selection(self):
        row = self.convert([self.raw, dict(self.raw, net_profit=100)])[0]
        self.assertIsNone(row['net_profit'])
        audit = json.loads(row['source_metadata']['conflict_null_audit'])
        self.assertEqual(set(audit['fields']['net_profit']), {'100.00', '123.45'})

    def test_small_symmetric_difference_selects_whole_row_stably_with_audit(self):
        candidates = [dict(self.raw, net_profit=100, total_profit=104),
                      dict(self.raw, net_profit=104, total_profit=100)]
        expected = self.convert(candidates)
        self.assertEqual(expected, self.convert(list(reversed(candidates))))
        row = expected[0]
        self.assertIn((row['net_profit'], row['total_profit']), [(100, 104), (104, 100)])
        audit = json.loads(row['source_metadata']['numeric_tolerance_audit'])
        self.assertEqual(audit['threshold'], '0.05')
        self.assertEqual(len(audit['candidates']), 2)
        from saa_collector.services.common.statement_version_writer import prepare_version
        prepare_version(TABLE, row)

    def test_symmetric_tolerance_boundary_and_negative_values(self):
        for a, b in [(97.5, 102.5), (-97.5, -102.5), (100, 105)]:
            with self.subTest(a=a, b=b):
                self.assertEqual(len(self.convert([dict(self.raw, net_profit=a),
                                                  dict(self.raw, net_profit=b)])), 1)
        for a, b in [(97.49, 102.5), (100, 105.2), (-100, 100), (0, 0.01), (None, 100)]:
            with self.subTest(a=a, b=b):
                row = self.convert([dict(self.raw, net_profit=a), dict(self.raw, net_profit=b)])[0]
                self.assertIsNone(row['net_profit'])

    def test_tolerance_compares_all_pairs_not_only_middle_candidate(self):
        for candidates in permutations([dict(self.raw, net_profit=n) for n in (100, 104, 108)]):
            self.assertIsNone(self.convert(list(candidates))[0]['net_profit'])

    def test_zero_and_rounding_follow_existing_field_precision(self):
        rows = self.convert([dict(self.raw, net_profit='0.001'), dict(self.raw, net_profit='-0.001')])
        self.assertEqual(rows[0]['net_profit'], 0)
        self.assertNotIn('numeric_tolerance_audit', rows[0]['source_metadata'])

    def test_failed_whole_row_tolerance_nullifies_all_disputed_fields(self):
        row = self.convert([dict(self.raw, net_profit=100, total_profit=100),
                            dict(self.raw, net_profit=104, total_profit=120)])[0]
        self.assertIsNone(row['net_profit'])
        self.assertIsNone(row['total_profit'])

    def test_tolerance_does_not_override_source_priority(self):
        rows = self.convert([dict(self.raw, net_profit=100, update_flag='0'),
                             dict(self.raw, net_profit=104, update_flag='1')])
        self.assertEqual(rows[0]['net_profit'], 104)
        self.assertNotIn('numeric_tolerance_audit', rows[0]['source_metadata'])

    def test_large_audit_is_rejected_not_truncated(self):
        with self.assertRaisesRegex(ValueError, 'conflict'):
            self.convert([dict(self.raw, net_profit=Decimal(100) + Decimal(i) / 100)
                          for i in range(100)])

    def test_missing_mapped_field_is_explicit_null_with_evidence(self):
        del self.raw['net_profit']
        row = self.convert([self.raw])[0]
        self.assertIsNone(row['net_profit'])
        self.assertEqual(json.loads(row['source_metadata']['missing_source_fields']),
                         {'net_profit': 'net_profit'})

    def test_same_day_updated_snapshot_wins_independent_of_order(self):
        old = dict(self.raw, update_flag='0')
        newer = dict(self.raw, update_flag='1', net_profit=None)
        for rows in ([old, newer], [newer, old]):
            result = self.convert(rows)
            self.assertEqual(len(result), 1)
            self.assertIsNone(result[0]['net_profit'])
            self.assertEqual(result[0]['source_metadata']['update_flag'], '1')

    def test_conflicting_updated_snapshots_degrade(self):
        row = self.convert([dict(self.raw, update_flag='1'),
                            dict(self.raw, update_flag='1', net_profit=999)])[0]
        self.assertIsNone(row['net_profit'])

    def test_report_types_coexist_independent_of_order(self):
        latest = dict(self.raw, report_type='1', update_flag='0', net_profit=None)
        adjusted = dict(self.raw, report_type='4', update_flag='1', net_profit=200)
        original = dict(self.raw, report_type='5', update_flag='1', net_profit=300)
        for records in permutations([latest, adjusted, original]):
            with self.subTest(order=[r['report_type'] for r in records]):
                rows = {r['version_type']: r for r in self.convert(records)}
                self.assertEqual(set(rows), {'LATEST', 'RESTATED', 'ORIGINAL'})
                row = rows['LATEST']
                self.assertIsNone(row['net_profit'])
                self.assertEqual(row['source_metadata']['report_type'], '1')
                self.assertEqual(row['source_metadata']['update_flag'], '0')

    def test_adjusted_does_not_replace_original_when_latest_is_absent(self):
        adjusted = dict(self.raw, report_type='4', update_flag='0', net_profit=200)
        original = dict(self.raw, report_type='5', update_flag='1', net_profit=300)
        for records in ([adjusted, original], [original, adjusted]):
            rows = self.convert(records)
            self.assertEqual(len(rows), 2)
            row = next(r for r in rows if r['version_type'] == 'RESTATED')
            self.assertEqual(row['net_profit'], Decimal('200.00'))
            self.assertEqual(row['source_metadata']['report_type'], '4')

    def test_update_flag_resolves_within_selected_type_only(self):
        records = [dict(self.raw, report_type='1', update_flag='0', net_profit=10),
                   dict(self.raw, report_type='1', update_flag='1', net_profit=20),
                   dict(self.raw, report_type='4', update_flag='1', net_profit=30)]
        for ordered in permutations(records):
            rows = {r['version_type']: r for r in self.convert(ordered)}
            self.assertEqual(rows['LATEST']['net_profit'], Decimal('20.00'))
            self.assertEqual(rows['RESTATED']['net_profit'], Decimal('30.00'))

    def test_same_rank_adjusted_sign_conflict_degrades(self):
        records = [dict(self.raw, report_type='4', update_flag='1', net_profit=value)
                   for value in (-172014721.27, 172014721.27)]
        for ordered in (records, records[::-1]):
            self.assertIsNone(self.convert(ordered)[0]['net_profit'])

    def test_different_disclosure_dates_are_not_compared_by_report_type(self):
        records = [dict(self.raw, report_type='1', net_profit=10),
                   dict(self.raw, report_type='4', f_ann_date='20250328', net_profit=20),
                   dict(self.raw, report_type='5', f_ann_date='20260328', net_profit=30)]
        rows = self.convert(records)
        self.assertEqual([r['net_profit'] for r in rows], list(map(Decimal, ('10', '20', '30'))))

    def test_source_dates_preserved_even_when_latest_content_has_older_f_ann_date(self):
        raw = dict(self.raw, ann_date='20250329', f_ann_date='20240329')
        row = self.convert([raw])[0]
        self.assertEqual(row['version_type'], 'LATEST')
        self.assertEqual(row['source_metadata']['ann_date'], '20250329')
        self.assertEqual(row['source_metadata']['f_ann_date'], '20240329')

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
        from saa_collector.services.common.statement_source_adapter import CompleteStatementHistory
        service = self.service()
        service.pro.query.side_effect = [pd.DataFrame([dict(ts_code='600036.SH',
            end_date='20231231', f_ann_date=day, report_type=kind, update_flag='1')])
            for day, kind in [('20240329', '1'), ('20250328', '4'), ('20240329', '5')]]
        rows = service.query_record('income', '600036', fields='ts_code,end_date')
        self.assertEqual(len(rows), 3)
        self.assertIsInstance(rows, CompleteStatementHistory)
        self.assertEqual([c.kwargs['report_type'] for c in service.pro.query.call_args_list], ['1', '4', '5'])

    def test_partial_type_query_does_not_certify_latest_absence(self):
        from saa_collector.services.common.statement_source_adapter import CompleteStatementHistory
        service = self.service()
        service.pro.query.return_value = pd.DataFrame([dict(ts_code='600036.SH', report_type='4')])
        self.assertNotIsInstance(service.query_record('income', '600036', report_type='4'),
                                 CompleteStatementHistory)

    def test_failed_historical_query_cannot_certify_empty_latest(self):
        service = self.service()
        service.pro.query.side_effect = [pd.DataFrame(), RuntimeError('upstream unavailable')]
        with self.assertRaisesRegex(RuntimeError, 'upstream unavailable'):
            service.query_record('income', '600036')

    def test_announcement_date_slice_cannot_certify_latest_absence(self):
        from saa_collector.services.common.statement_source_adapter import CompleteStatementHistory
        for params in ({'start_date': '20240101'}, {'end_date': '20241231'}):
            service = self.service()
            service.pro.query.side_effect = [pd.DataFrame(), pd.DataFrame([
                dict(ts_code='600036.SH', report_type='4')]), pd.DataFrame()]
            with self.subTest(params=params):
                self.assertNotIsInstance(service.query_record('income', '600036', **params),
                                         CompleteStatementHistory)

    def test_transform_derives_only_from_completed_query(self):
        from saa_collector.services.common.statement_source_adapter import CompleteStatementHistory
        service = self.service()
        fixture = TushareStatementVersionsTest()
        fixture.setUp()
        service.config_service.get_table_config.return_value = fixture.mapping
        raw = [dict(fixture.raw, report_type='4')]
        self.assertEqual(len(service.transform_records(raw, TABLE)), 1)
        self.assertEqual(len(service.transform_records(CompleteStatementHistory(raw), TABLE)), 2)

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

    def test_typed_conflict_is_recorded_and_next_symbol_is_processed(self):
        from saa_collector.services.collect_job_result import merge_issue
        from saa_collector.services.common.statement_version_writer import (
            StatementVersionConflict, conflict_issue,
        )
        row = dict.fromkeys(financial_fields(TABLE), None)
        row.update(symbol='600036', provider='tushare', version_type='LATEST',
                   report_date=date(2023, 12, 31), disclosure_date=date(2024, 3, 29),
                   net_profit=Decimal('100'))
        issue = conflict_issue(TABLE, row, dict(row, net_profit=Decimal('200')))
        service = self.service()
        service._produce_one = MagicMock(side_effect=[
            StatementVersionConflict('conflict', issue=issue), None])
        result = {}

        def record(payload):
            nonlocal result
            result = merge_issue(result, payload, 'now')

        failed, success = MagicMock(), MagicMock()
        with patch('saa_collector.services.impl.tushare.statement_service.ProgressLogger'):
            service.produce(['600036', '600000'], on_symbol_issue=record,
                            on_symbol_failure=failed, on_symbol_success=success)
        failed.assert_called_once_with('600036')
        success.assert_called_once_with('600000')
        self.assertEqual(service._produce_one.call_count, 2)
        self.assertEqual(result['issues'][0]['version_type'], 'LATEST')
        self.assertEqual(result['issues'][0]['differences'], issue['differences'])

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

    def test_null_warning_survives_success_and_does_not_leak_to_next_symbol(self):
        from saa_collector.services.collect_job_result import merge_issue, resolve_symbol
        service = self.service()
        issue = dict(code='STATEMENT_FIELD_NULLIFIED', symbol='600036',
                     action='STORE_NULL_CONTINUE', differences={'asset_impairment_loss':
                     {'source_value': '123', 'stored_value': None, 'reason': 'missing anchors'}})
        result = {}
        events = []

        def produce(symbol, start_date):
            if symbol == '600036':
                service._committed_field_issues = [issue]

        def success(symbol):
            nonlocal result
            events.append(('success', symbol))
            result = resolve_symbol(result, symbol, 'now')

        def record(payload):
            nonlocal result
            events.append(('warning', payload['symbol']))
            result = merge_issue(result, payload, 'now')

        service._produce_one = produce
        failed = MagicMock()
        with patch('saa_collector.services.impl.tushare.statement_service.ProgressLogger'):
            service.produce(['600036', '600000'], on_symbol_issue=record,
                            on_symbol_success=success, on_symbol_failure=failed)
        failed.assert_not_called()
        self.assertEqual(events, [('success', '600036'), ('warning', '600036'), ('success', '600000')])
        self.assertIsNone(result['issues'][0]['resolved_at'])
        self.assertEqual(result['issues'][0]['occurrences'], 1)

    def test_field_warning_only_emitted_after_bundle_commit(self):
        service = self.service()
        fixture = TushareStatementVersionsTest()
        fixture.setUp()
        del fixture.raw['net_profit']
        converted = fixture.convert([fixture.raw])
        service.query_record = MagicMock(return_value=[])
        service.build_fields = MagicMock(return_value='')
        service.transform_records = MagicMock(return_value=converted)
        service.collect_dividend = MagicMock()
        service._committed_field_issues = []
        with patch('saa_collector.services.impl.tushare.statement_service.save_version_bundle',
                   side_effect=RuntimeError('rollback')):
            with self.assertRaisesRegex(RuntimeError, 'rollback'):
                service._collect_one('600036')
        self.assertEqual(service._committed_field_issues, [])
        with patch('saa_collector.services.impl.tushare.statement_service.save_version_bundle'):
            service._collect_one('600036')
        self.assertTrue(service._committed_field_issues)
        self.assertEqual(service._committed_field_issues[0]['code'], 'STATEMENT_SOURCE_FIELDS_MISSING')

    def test_issue_persistence_failure_is_not_swallowed(self):
        service = self.service()
        service.build_symbols = MagicMock(return_value=['600036'])
        service._produce_one = MagicMock(side_effect=ValueError('secret upstream response'))
        issue_sink = MagicMock(side_effect=RuntimeError('cannot persist'))
        with patch('saa_collector.services.impl.tushare.statement_service.ProgressLogger'):
            with self.assertRaisesRegex(RuntimeError, 'cannot persist'):
                service.produce(['600036'], on_symbol_issue=issue_sink)
        self.assertNotIn('secret', str(issue_sink.call_args))
