# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch

from saa_collector.services.common import statement_maintain_service as module
from saa_collector.services.common.statement_maintain_service import StatementMaintainService


class StatementMaintainServiceTest(unittest.TestCase):
    def test_candidate_builder_preserves_inputs_and_reports_missing_dependencies(self):
        from datetime import date
        from copy import deepcopy
        service = self.build_service()
        rows = [dict(symbol='A', date=date(2024, 6, 30), net_profit=60),
                dict(symbol='B', date=date(2024, 6, 30), net_profit=30),
                dict(symbol='A', date=date(2023, 12, 31), net_profit=100),
                dict(symbol='A', date=date(2023, 6, 30), net_profit=40)]
        before = deepcopy(rows)
        candidates, missing = service.build_ttm_candidates(rows, ['net_profit'])
        self.assertEqual([(r['symbol'], r['net_profit']) for r in candidates], [('A', 120)])
        self.assertEqual(missing, ['B'])
        self.assertEqual(rows, before)

    def test_candidate_builder_rejects_duplicate_periods(self):
        from datetime import date
        service = self.build_service()
        row = dict(symbol='A', report_date=date(2023, 12, 31), net_profit=100)
        with self.assertRaises(ValueError):
            service.build_ttm_candidates([row, dict(row)], ['net_profit'])

    def test_candidate_builder_handles_empty_and_preserves_null_arithmetic(self):
        from datetime import date
        service = self.build_service()
        self.assertEqual(service.build_ttm_candidates([], ['net_profit']), ([], []))
        rows = [dict(symbol='A', report_date=period, net_profit=value)
                for period, value in [(date(2024, 6, 30), None),
                                      (date(2023, 12, 31), 100),
                                      (date(2023, 6, 30), 40)]]
        candidates, missing = service.build_ttm_candidates(rows, ['net_profit'])
        self.assertEqual(candidates[0]['net_profit'], 60)
        self.assertEqual(missing, [])

    def build_service(self):
        with patch.object(module, 'ConfigService') as config_service_class:
            config_service_class.return_value.get_db_config.return_value = {}
            config_service_class.return_value.get_config.return_value = {}
            return StatementMaintainService()

    def test_version_mode_process_publishes_both_caches_once(self):
        service = self.build_service()
        service.config_service.get_config.return_value = {
            'saa_collector': {'statement_versioning': {'enabled': True}}}
        service.publish_caches = MagicMock()
        service.refresh_financial_report_cache = MagicMock()
        service.refresh_ttm_report_cache = MagicMock()
        service.process('600036')
        service.publish_caches.assert_called_once_with('600036')
        service.refresh_financial_report_cache.assert_not_called()
        service.refresh_ttm_report_cache.assert_not_called()

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

    def test_financial_fields_exclude_new_and_unknown_metadata(self):
        import pandas as pd
        service = self.build_service()
        service.config_service.get_table_config.return_value = pd.DataFrame({
            'Field': ['symbol', 'report_date', 'net_profit', 'id', 'provider',
                      'source_metadata', 'content_hash', 'future_metadata']})
        self.assertEqual(service.get_fields('saa_raw_income_statement'), ['net_profit'])

    def test_interleaved_securities_keep_all_ttm_dependencies(self):
        from datetime import date
        service = self.build_service()
        service.get_fields = MagicMock(side_effect=[['net_profit'], []])
        connection = MagicMock()
        rows = []
        for report_date, value in [(date(2024, 6, 30), 60),
                                   (date(2023, 12, 31), 100),
                                   (date(2023, 6, 30), 40)]:
            for symbol in ['000001', '000002']:
                rows.append({'symbol': symbol, 'report_date': report_date,
                             'net_profit': value})
        connection.cursor.return_value.fetchall.return_value = rows
        with patch.object(module.mysql.connector, 'connect', return_value=connection), \
                patch.object(module, 'DB') as db_class:
            service.refresh_ttm_report_cache(['000001', '000002'])
        result = db_class.return_value.to_sql.call_args.args[0]
        self.assertEqual([(r['symbol'], r['net_profit']) for r in result],
                         [('000001', 120), ('000002', 120)])


if __name__ == '__main__':
    unittest.main()
