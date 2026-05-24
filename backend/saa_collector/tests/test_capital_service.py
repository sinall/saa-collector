from unittest import TestCase

from saa_collector.services.impl.tushare.capital_service import CapitalServiceImpl


class CapitalRecordTransformTest(TestCase):
    def test_capital_record_skips_rows_without_base_share(self):
        service = CapitalServiceImpl.__new__(CapitalServiceImpl)

        record = service.build_capital_record({
            'ts_code': '000001.SZ',
            'base_share': None,
            'stk_bo_rate': None,
            'stk_co_rate': None,
            'ex_date': '20240101',
        })

        self.assertIsNone(record)

    def test_capital_record_defaults_empty_bonus_rates_to_zero(self):
        service = CapitalServiceImpl.__new__(CapitalServiceImpl)

        record = service.build_capital_record({
            'ts_code': '000001.SZ',
            'base_share': 10,
            'stk_bo_rate': None,
            'stk_co_rate': None,
            'ex_date': '20240101',
        })

        self.assertEqual(record, {
            'symbol': '000001',
            'date': '2024-01-01',
            'capital': 100000,
        })
