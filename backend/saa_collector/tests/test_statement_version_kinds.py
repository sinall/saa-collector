"""Version kind contracts; no database or production settings."""
import unittest
from datetime import date
from unittest.mock import Mock

from saa_collector.services.common.financial_statement_contract import financial_fields, latest_view_sql
from saa_collector.services.common.statement_version_writer import prepare_version, write_versions


TABLE = 'saa_raw_income_statement'


class StatementVersionKindsTest(unittest.TestCase):
    def row(self, kind='LATEST'):
        return dict(dict.fromkeys(financial_fields(TABLE)), symbol='600036',
                    report_date=date(2023, 12, 31), disclosure_date=date(2024, 3, 29),
                    version_type=kind, provider='tushare',
                    source_metadata={'report_type': '1', 'ann_date': '20240329',
                                     'f_ann_date': '20240329'})

    def test_prepared_kind_and_source_dates_survive(self):
        row = self.row()
        result = prepare_version(TABLE, row)
        self.assertEqual(result['version_type'], 'LATEST')
        self.assertIn('f_ann_date', result['source_metadata'])
        with self.assertRaises(ValueError):
            prepare_version(TABLE, self.row('unexpected'))

    def test_typed_write_refuses_old_daily_index(self):
        connection = Mock(in_transaction=True, autocommit=False)
        cursor = connection.cursor.return_value
        cursor.fetchall.return_value = [dict(Key_name=name, Non_unique=0,
            Seq_in_index=i, Column_name=column, Sub_part=None)
            for name, columns in [('PRIMARY', ['id']), ('uq_statement_disclosure',
                ['symbol', 'report_date', 'disclosure_date'])]
            for i, column in enumerate(columns, 1)]
        with self.assertRaisesRegex(ValueError, 'migration'):
            write_versions(connection, TABLE, [self.row()])
        self.assertFalse(any('INSERT' in c.args[0] for c in cursor.execute.call_args_list))

    def test_typed_duplicate_lookup_includes_kind(self):
        from mysql.connector import IntegrityError
        connection = Mock(in_transaction=True, autocommit=False)
        cursor = connection.cursor.return_value
        cursor.fetchall.return_value = [dict(Key_name=name, Non_unique=0,
            Seq_in_index=i, Column_name=column, Sub_part=None)
            for name, columns in [('PRIMARY', ['id']), ('uq_statement_version',
                ['symbol', 'report_date', 'disclosure_date', 'version_type'])]
            for i, column in enumerate(columns, 1)]
        cursor.fetchall.side_effect = [cursor.fetchall.return_value, []]
        cursor.execute.side_effect = [None, None, IntegrityError(errno=1062), None]
        cursor.fetchone.return_value = dict(prepare_version(TABLE, self.row()), id=7)
        self.assertEqual(write_versions(connection, TABLE, [self.row()]),
                         [{'id': 7, 'created': False}])
        sql, params = cursor.execute.call_args.args
        self.assertIn('version_type=%s', sql)
        self.assertEqual(params[-1], 'LATEST')

    def test_latest_projection_filters_both_join_sides(self):
        sql = latest_view_sql(TABLE, ['symbol', 'report_date', 'disclosure_date'], versioned=True)
        self.assertIn("WHERE version_type = 'LATEST'", sql)
        self.assertIn("r.version_type = 'LATEST'", sql)

    def test_migration_packet_has_no_cache_rebuild_or_original_copies(self):
        from saa_collector.services.common.statement_kind_migration import render_packet
        packet = render_packet()
        self.assertEqual(set(packet), {'01-version-kinds.sql', '02-latest-views.sql'})
        sql = packet['01-version-kinds.sql']
        self.assertNotIn('INSERT', sql)
        self.assertNotIn('ttm_reports_cache', sql)
        self.assertIn("THEN 'ORIGINAL'", sql)
        self.assertIn("ELSE 'LATEST'", sql)
        self.assertIn('`version_type`', sql)
        self.assertIn('DROP INDEX `uq_statement_disclosure`', sql)
        self.assertEqual(packet['02-latest-views.sql'].count("r.version_type = 'LATEST'"), 3)

    def test_production_packet_preserves_captured_view_headers(self):
        from saa_collector.services.common.statement_kind_migration import render_packet
        from saa_collector.services.common.statement_migration_plan import TABLES
        captured = {table.replace('saa_raw_', 'saa_latest_'):
            'CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`%` SQL SECURITY INVOKER VIEW '
            '`{}` AS SELECT 1'.format(table.replace('saa_raw_', 'saa_latest_'))
            for table in TABLES}
        sql = render_packet(show_create_views=captured)['02-latest-views.sql']
        self.assertEqual(sql.count('DEFINER=`root`@`%` SQL SECURITY INVOKER'), 3)
        self.assertEqual(sql.count('CREATE OR REPLACE ALGORITHM=UNDEFINED'), 3)
        with self.assertRaises(ValueError):
            render_packet(show_create_views={})
        captured['saa_latest_income_statement'] = captured['saa_latest_balance_sheet']
        with self.assertRaises(ValueError):
            render_packet(show_create_views=captured)
