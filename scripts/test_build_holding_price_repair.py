import importlib.util
from pathlib import Path
import unittest


class RepairPlanTest(unittest.TestCase):
    def test_missing_flags_split_types_and_deduplicate_stock_dates(self):
        path = Path(__file__).with_name('build_holding_price_repair.py')
        self.assertTrue(path.exists(), 'offline repair request builder is missing')
        spec = importlib.util.spec_from_file_location('repair', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        row = {'code': '000001', 'return_date': '2025-06-30', 'missing_exact_price': 'True', 'missing_exact_adjustment': 'True'}
        plan = module.build_plan([row, dict(row), dict(row, code='000002', missing_exact_price='False')])
        jobs = {job['data_type']: job for job in plan['jobs']}
        self.assertEqual(jobs['historical_quote']['symbols'], ['000001'])
        self.assertEqual(jobs['price_adjust_factor']['symbols'], ['000001', '000002'])
        self.assertEqual(jobs['price_adjust_factor']['start_date'], '2025-06-30')
        self.assertFalse(jobs['price_adjust_factor']['skip_existing'])
        self.assertEqual(jobs['price_adjust_factor']['stock_scope'], 'SELECTED')

    def test_multiple_months_merge_into_one_range_per_type(self):
        path = Path(__file__).with_name('build_holding_price_repair.py')
        spec = importlib.util.spec_from_file_location('repair', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        row = {'code': '000001', 'return_date': '2025-01-31', 'missing_exact_price': 'True', 'missing_exact_adjustment': 'True'}
        plan = module.build_plan([row, dict(row, code='000002', return_date='2025-06-30')])
        self.assertEqual(len(plan['jobs']), 2)
        for job in plan['jobs']:
            self.assertEqual(job['start_date'], '2025-01-31')
            self.assertEqual(job['end_date'], '2025-06-30')
            self.assertEqual(job['data_frequency'], 'monthly')
            self.assertEqual(job['symbols'], ['000001', '000002'])
