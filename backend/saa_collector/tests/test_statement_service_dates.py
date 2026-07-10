from unittest import TestCase
from unittest.mock import MagicMock, patch

import pandas as pd

from saa_collector.services.impl.tushare import statement_service as module
from saa_collector.services.impl.tushare.statement_service import StatementServiceImpl


class StatementServiceDateMappingTest(TestCase):
    def build_service(self):
        with patch.object(module.BasicStockService, '__init__', return_value=None), \
             patch.object(module, 'StatementMaintainService'):
            service = StatementServiceImpl()
            service._logger = MagicMock()
            service.config_service = MagicMock()
            service.config = {'saa_collector': {'tushare_api': {}}}
            return service

    def test_transform_statement_records_maps_report_and_disclosure_dates(self):
        service = self.build_service()
        service.config_service.get_table_config.return_value = pd.DataFrame([
            {'Field': 'symbol', 'TushareField': 'ts_code', 'TushareUnit': 1},
            {'Field': 'date', 'TushareField': 'end_date', 'TushareUnit': 1},
            {'Field': 'net_profit', 'TushareField': 'n_income', 'TushareUnit': 1},
        ])

        records = service.transform_records([
            {
                'ts_code': '000001.SZ',
                'end_date': '20231231',
                'f_ann_date': '20240315',
                'ann_date': '20240320',
                'n_income': 123,
            },
        ], 'saa_raw_income_statement')

        self.assertEqual(records, [{
            'symbol': '000001',
            'report_date': '2023-12-31',
            'disclosure_date': '2024-03-15',
            'net_profit': 123,
        }])

    def test_transform_statement_records_falls_back_to_ann_date(self):
        service = self.build_service()
        service.config_service.get_table_config.return_value = pd.DataFrame([
            {'Field': 'symbol', 'TushareField': 'ts_code', 'TushareUnit': 1},
            {'Field': 'date', 'TushareField': 'end_date', 'TushareUnit': 1},
        ])

        records = service.transform_records([
            {
                'ts_code': '000001.SZ',
                'end_date': '20230930',
                'f_ann_date': None,
                'ann_date': '20231028',
            },
        ], 'saa_raw_balance_sheet')

        self.assertEqual(records[0]['report_date'], '2023-09-30')
        self.assertEqual(records[0]['disclosure_date'], '2023-10-28')

    def test_save_statements_uses_report_date_primary_key(self):
        service = self.build_service()
        service.save_records = MagicMock()

        records = [{'symbol': '000001', 'report_date': '2023-12-31'}]
        service.save_statements(records, 'saa_raw_income_statement')

        service.save_records.assert_called_once_with(
            records,
            'saa_raw_income_statement',
            ['symbol', 'report_date'],
        )
