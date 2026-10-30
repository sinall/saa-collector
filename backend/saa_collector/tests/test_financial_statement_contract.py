import unittest
from datetime import date
from decimal import Decimal

from saa_collector.services.common import financial_statement_contract as contract


class FinancialStatementContractTest(unittest.TestCase):
    table = 'saa_raw_income_statement'

    def row(self):
        result = dict.fromkeys(contract.financial_fields(self.table))
        result.update(symbol='000001', report_date=date(2023, 12, 31),
                      disclosure_date=date(2024, 3, 30), net_profit=Decimal('100.00'))
        return result

    def test_hash_ignores_provider_but_distinguishes_null_and_zero(self):
        row = self.row()
        first = contract.content_hash(self.table, row)
        row.update(provider='akshare', source_metadata={'upstream': 'sina'}, id=99)
        row['net_profit'] = Decimal('100.0000')
        self.assertEqual(contract.content_hash(self.table, row), first)
        row['net_profit'] = None
        missing = contract.content_hash(self.table, row)
        row['net_profit'] = 0
        self.assertNotEqual(contract.content_hash(self.table, row), missing)

    def test_missing_field_is_not_silently_assigned_null(self):
        row = self.row()
        del row['net_profit']
        with self.assertRaises(ValueError):
            contract.content_hash(self.table, row)

    def test_daily_identity_requires_dates(self):
        row = self.row()
        self.assertEqual(contract.disclosure_identity(row),
                         ('000001', date(2023, 12, 31), date(2024, 3, 30)))
        row['disclosure_date'] = None
        with self.assertRaises(ValueError):
            contract.disclosure_identity(row)

    def test_nonfinite_values_are_not_hashable(self):
        row = self.row()
        row['net_profit'] = float('nan')
        with self.assertRaises(ValueError):
            contract.content_hash(self.table, row)
