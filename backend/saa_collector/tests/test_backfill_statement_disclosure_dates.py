from datetime import date
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase


class BackfillStatementDisclosureDatesCommandTest(SimpleTestCase):
    def call_command(self, *args):
        out = StringIO()
        call_command('backfill_statement_disclosure_dates', *args, stdout=out)
        return out.getvalue()

    @patch('saa_collector.management.commands.backfill_statement_disclosure_dates.StatementServiceImpl')
    @patch('saa_collector.management.commands.backfill_statement_disclosure_dates.resolve_symbols')
    def test_dry_run_estimates_requests_without_querying_tushare(self, resolve_symbols, service_class):
        resolve_symbols.return_value = ['000001', '000002']

        output = self.call_command('--symbols', '000001', '000002', '--dry-run')

        self.assertIn('symbols=2', output)
        self.assertIn('estimated_tushare_requests=6', output)
        service_class.assert_not_called()

    def test_requires_exactly_one_scope(self):
        with self.assertRaises(CommandError):
            self.call_command('--dry-run')

        with self.assertRaises(CommandError):
            self.call_command('--symbols', '000001', '--index', '000906', '--dry-run')

    @patch('saa_collector.management.commands.backfill_statement_disclosure_dates.update_disclosure_dates')
    @patch('saa_collector.management.commands.backfill_statement_disclosure_dates.StatementServiceImpl')
    @patch('saa_collector.management.commands.backfill_statement_disclosure_dates.resolve_symbols')
    def test_backfills_three_statement_resources_only(
            self, resolve_symbols, service_class, update_disclosure_dates):
        resolve_symbols.return_value = ['000001']
        service = MagicMock()
        service_class.return_value = service
        service.build_fields.side_effect = lambda table, sub_resource=None: f'fields-{sub_resource}'
        service.build_date_param.side_effect = lambda value: value.strftime('%Y%m%d') if value else None
        service.query_record.side_effect = [
            [{'ts_code': '000001.SZ', 'end_date': '20231231', 'f_ann_date': '20240315'}],
            [{'ts_code': '000001.SZ', 'end_date': '20231231', 'ann_date': '20240320'}],
            [{'ts_code': '000001.SZ', 'end_date': '20231231', 'f_ann_date': '20240325'}],
        ]
        service.transform_records.side_effect = [
            [{'symbol': '000001', 'report_date': date(2023, 12, 31), 'disclosure_date': date(2024, 3, 15)}],
            [{'symbol': '000001', 'report_date': date(2023, 12, 31), 'disclosure_date': date(2024, 3, 20)}],
            [{'symbol': '000001', 'report_date': date(2023, 12, 31), 'disclosure_date': date(2024, 3, 25)}],
        ]
        update_disclosure_dates.return_value = 1

        output = self.call_command('--symbols', '000001', '--start-date', '2009-01-01')

        self.assertIn('updated_rows=3', output)
        self.assertEqual(
            [call.args[0] for call in service.query_record.call_args_list],
            ['balancesheet', 'income', 'cashflow'],
        )
        self.assertEqual(update_disclosure_dates.call_count, 3)
        self.assertEqual(
            [call.args[0] for call in update_disclosure_dates.call_args_list],
            ['saa_raw_balance_sheet', 'saa_raw_income_statement', 'saa_raw_cash_flow_statement'],
        )

    @patch('saa_collector.management.commands.backfill_statement_disclosure_dates.connection')
    def test_index_scope_uses_historical_constituent_union(self, connection):
        cursor = MagicMock()
        cursor.fetchall.return_value = [('000002',), ('000001',)]
        connection.cursor.return_value.__enter__.return_value = cursor

        output = self.call_command('--index', '000906', '--dry-run')

        self.assertIn('symbols=2', output)
        cursor.execute.assert_called_once()
        self.assertIn('saa_index_weights', cursor.execute.call_args.args[0])
