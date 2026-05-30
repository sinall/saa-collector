from io import StringIO
from unittest.mock import MagicMock, Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from saa_collector.services.common.mfactor_readiness_service import (
    MfactorReadinessService,
)


class MfactorReadinessServiceTest(SimpleTestCase):
    def test_check_reports_required_table_counts_and_max_dates(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [
            ('BASE TABLE',), (1,), (10,), ('2026-05-30',),
        ]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor

        results = MfactorReadinessService(connection=connection, requirements=[
            {
                'name': 'Trading calendar',
                'object': 'saa_trade_days',
                'date_column': 'date',
            },
        ]).check()

        self.assertEqual(results['status'], 'OK')
        self.assertEqual(results['summary'], {'ok': 1, 'error': 0})
        self.assertEqual(results['items'][0]['status'], 'OK')
        self.assertEqual(results['items'][0]['object_type'], 'BASE TABLE')
        self.assertEqual(results['items'][0]['row_count'], 10)
        self.assertEqual(results['items'][0]['max_date'], '2026-05-30')

    def test_check_only_verifies_view_definition_by_default(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [
            ('VIEW',),
        ]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor

        results = MfactorReadinessService(connection=connection, requirements=[
            {
                'name': 'Monthly prices',
                'object': 'saa_monthly_prices',
                'date_column': 'report_date',
            },
        ]).check()

        executed_sql = '\n'.join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertEqual(results['status'], 'OK')
        self.assertEqual(results['items'][0]['object_type'], 'VIEW')
        self.assertIsNone(results['items'][0]['row_count'])
        self.assertIsNone(results['items'][0]['max_date'])
        self.assertNotIn('SELECT 1 FROM `saa_monthly_prices` LIMIT 1', executed_sql)
        self.assertNotIn('COUNT(*) FROM `saa_monthly_prices`', executed_sql)
        self.assertNotIn('MAX(`report_date`) FROM `saa_monthly_prices`', executed_sql)

    def test_check_can_run_deep_metrics_for_views(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [
            ('VIEW',), (1,), (8,), ('2026-03-31',),
        ]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor

        results = MfactorReadinessService(connection=connection, deep=True, requirements=[
            {
                'name': 'Combined financial statements',
                'object': 'saa_financial_statements_combined',
                'date_column': 'date',
            },
        ]).check()

        self.assertEqual(results['status'], 'OK')
        self.assertEqual(results['items'][0]['row_count'], 8)
        self.assertEqual(results['items'][0]['max_date'], '2026-03-31')

    def test_deep_check_reports_empty_views_as_errors(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [
            ('VIEW',), None,
        ]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor

        results = MfactorReadinessService(connection=connection, deep=True, requirements=[
            {
                'name': 'Monthly prices',
                'object': 'saa_monthly_prices',
                'date_column': 'report_date',
            },
        ]).check()

        self.assertEqual(results['status'], 'ERROR')
        self.assertEqual(results['items'][0]['row_count'], 0)
        self.assertEqual(results['items'][0]['message'], 'object is empty')

    def test_check_reports_missing_objects_as_errors(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [None]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor

        results = MfactorReadinessService(connection=connection, requirements=[
            {'name': 'Index weights', 'object': 'saa_index_weights', 'date_column': 'date'},
        ]).check()

        self.assertEqual(results['status'], 'ERROR')
        self.assertEqual(results['summary'], {'ok': 0, 'error': 1})
        self.assertEqual(results['items'][0]['status'], 'ERROR')
        self.assertEqual(results['items'][0]['message'], 'object not found')


class MfactorReadinessCommandTest(SimpleTestCase):
    @patch('saa_collector.management.commands.check_mfactor_readiness.MfactorReadinessService')
    def test_command_outputs_summary(self, service_class):
        service_class.return_value.check.return_value = {
            'status': 'OK',
            'summary': {'ok': 1, 'error': 0},
            'items': [
                {
                    'status': 'OK',
                    'name': 'Trading calendar',
                    'object': 'saa_trade_days',
                    'object_type': 'BASE TABLE',
                    'row_count': 10,
                    'max_date': '2026-05-30',
                    'message': '',
                },
            ],
        }
        out = StringIO()

        call_command('check_mfactor_readiness', stdout=out)

        self.assertIn('mfactor readiness: OK', out.getvalue())
        self.assertIn('saa_trade_days', out.getvalue())
        service_class.assert_called_once_with(deep=False)

    @patch('saa_collector.management.commands.check_mfactor_readiness.MfactorReadinessService')
    def test_command_supports_deep_metrics(self, service_class):
        service_class.return_value.check.return_value = {
            'status': 'OK',
            'summary': {'ok': 0, 'error': 0},
            'items': [],
        }

        call_command('check_mfactor_readiness', deep=True)

        service_class.assert_called_once_with(deep=True)

    @patch('saa_collector.management.commands.check_mfactor_readiness.MfactorReadinessService')
    def test_command_can_fail_on_error(self, service_class):
        service_class.return_value.check.return_value = {
            'status': 'ERROR',
            'summary': {'ok': 0, 'error': 1},
            'items': [],
        }

        with self.assertRaises(CommandError):
            call_command('check_mfactor_readiness', fail_on_error=True)
