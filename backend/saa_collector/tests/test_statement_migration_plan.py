import unittest
from datetime import date

from saa_collector.services.common import financial_statement_contract as contract
from saa_collector.services.common.statement_migration_plan import (
    legacy_snapshot, shadow_statements, latest_combined_definition, cutover_rename_sql,
    combined_view_cutover_sql, pre_ingestion_restore_sql,
)


class StatementMigrationPlanTest(unittest.TestCase):
    table = 'saa_raw_income_statement'

    def test_restore_keeps_all_migrated_tables_without_drop(self):
        sql = pre_ingestion_restore_sql('20261031')
        self.assertEqual(sql.count('_pit_retained_20261031`'), 3)
        self.assertEqual(sql.count('_legacy_20261031` TO'), 3)
        self.assertEqual(sql.count('RENAME TABLE'), 1)
        self.assertNotIn('DROP', sql)
        with self.assertRaises(ValueError):
            pre_ingestion_restore_sql('bad;tag')

    def test_view_cutover_preserves_show_create_security_header(self):
        header = ('CREATE ALGORITHM=UNDEFINED DEFINER=`service`@`%` SQL SECURITY DEFINER '
                  'VIEW `saa`.`saa_financial_statements_combined` AS ')
        query = ('SELECT b.symbol FROM saa_raw_balance_sheet b '
                 'LEFT JOIN saa_raw_income_statement i USING(symbol,report_date) '
                 'LEFT JOIN saa_raw_cash_flow_statement c USING(symbol,report_date)')
        original = header + query
        changed = combined_view_cutover_sql(original)
        self.assertEqual(changed, header.replace('CREATE ', 'CREATE OR REPLACE ', 1)
                         + latest_combined_definition(query))
        for invalid in (original.replace('saa_financial_statements_combined', 'other_view'),
                        original + '; DROP TABLE x', query):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                combined_view_cutover_sql(invalid)

    def test_cutover_renames_all_three_tables_in_one_statement(self):
        sql = cutover_rename_sql('20261031_review')
        self.assertEqual(sql.count('RENAME TABLE'), 1)
        self.assertEqual(sql.count('_pit_shadow` TO'), 3)
        self.assertEqual(sql.count('_legacy_20261031_review`'), 3)
        self.assertNotIn('DROP', sql)
        for invalid in ('', '../backup', 'x; DROP TABLE x', 'a' * 30):
            with self.assertRaises(ValueError):
                cutover_rename_sql(invalid)

    def test_combined_rewrites_only_three_input_identifiers(self):
        original = ("SELECT bs.symbol, 'saa_raw_income_statement' AS literal "
                    "FROM `saa`.`saa_raw_balance_sheet` bs "
                    "LEFT JOIN `saa`.`saa_raw_income_statement` is_ USING(symbol,report_date) "
                    "LEFT JOIN `saa`.`saa_raw_cash_flow_statement` cfs USING(symbol,report_date)")
        changed = latest_combined_definition(original)
        self.assertIn("'saa_raw_income_statement' AS literal", changed)
        for name in ('balance_sheet', 'income_statement', 'cash_flow_statement'):
            self.assertIn('`saa_latest_' + name + '`', changed)
        self.assertEqual(changed.replace('`saa_latest_', '`saa_raw_'), original)
        for invalid in ('SELECT 1', original + '; SELECT 2',
                        original.replace('saa_raw_income_statement`', 'saa_latest_income_statement`')):
            with self.assertRaises(ValueError):
                latest_combined_definition(invalid)

    def test_only_reviewed_table_and_complete_column_contract(self):
        columns = ['symbol', 'report_date', 'disclosure_date',
                   *contract.financial_fields(self.table)]
        sql = shadow_statements(self.table, columns)
        self.assertEqual(len(sql), 2)
        self.assertIn('CREATE TABLE `saa_raw_income_statement_pit_shadow` LIKE', sql[0])
        self.assertIn('PRIMARY KEY (`id`)', sql[1])
        self.assertIn('(`symbol`,`report_date`,`disclosure_date`)', sql[1])
        self.assertNotIn('RENAME', ' '.join(sql))
        for table, cols in [('unexpected', columns), (self.table, columns[:-1]),
                            (self.table, columns + ['secret'])]:
            with self.assertRaises(ValueError):
                shadow_statements(table, cols)

    def test_legacy_snapshot_does_not_guess_provider_or_dates(self):
        row = dict.fromkeys(contract.financial_fields(self.table))
        row.update(symbol='600036', report_date=date(2012, 12, 31),
                   disclosure_date=date(2013, 3, 29), net_profit='100.00')
        version = legacy_snapshot(self.table, row)
        self.assertEqual(version['provider'], 'unknown')
        self.assertIsNone(version['source_metadata'])
        self.assertEqual(str(version['net_profit']), '100.00')
        self.assertNotIn('provider', row)
        with self.assertRaises(ValueError):
            legacy_snapshot(self.table, dict(row, disclosure_date=None))
        with self.assertRaises(ValueError):
            legacy_snapshot(self.table, dict(row, provider='tushare'))
