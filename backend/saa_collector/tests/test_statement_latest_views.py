import sqlite3
import unittest
from saa_collector.services.common import financial_statement_contract as contract


class LatestStatementViewTest(unittest.TestCase):
    def test_complete_latest_rows_keep_all_periods_and_hide_metadata(self):
        table = 'saa_raw_income_statement'
        columns = ['symbol', 'report_date', 'disclosure_date', 'net_profit']
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE '+table+' (symbol TEXT, report_date TEXT, '
                       'disclosure_date TEXT, net_profit NUMERIC, provider TEXT)')
            db.executemany('INSERT INTO '+table+' VALUES (?, ?, ?, ?, ?)', [
                ('A', '2022-12-31', '2023-03-30', 100, 'x'),
                ('A', '2022-12-31', '2024-03-30', 90, 'y'),
                ('A', '2023-12-31', '2024-04-01', 110, 'x'),
                ('B', '2022-12-31', '2023-04-01', 80, 'x')])
            db.execute(contract.latest_view_sql(table, columns))
            cursor = db.execute('SELECT * FROM saa_latest_income_statement ORDER BY symbol, report_date')
            self.assertEqual([c[0] for c in cursor.description], columns)
            self.assertEqual(cursor.fetchall(), [
                ('A', '2022-12-31', '2024-03-30', 90),
                ('A', '2023-12-31', '2024-04-01', 110),
                ('B', '2022-12-31', '2023-04-01', 80)])

    def test_unknown_names_and_metadata_are_rejected(self):
        for table, columns in [('arbitrary_table', ['symbol']),
                               ('saa_raw_income_statement', ['symbol', 'provider'])]:
            with self.assertRaises(ValueError):
                contract.latest_view_sql(table, columns)
