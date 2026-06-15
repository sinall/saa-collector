from types import SimpleNamespace
from datetime import date
from unittest.mock import patch

from django.test import SimpleTestCase

from saa_collector.services.collect_plan_executor import execute_collect


class IndustryStocksMonthlyRoutingTest(SimpleTestCase):
    @patch('saa_collector.services.collect_plan_executor.resolve_month_end_trade_dates')
    @patch('saa_collector.services.common.sw_industry_service.SwIndustryService')
    def test_execute_collect_routes_industry_stocks_jobs_to_month_end_dates(
            self, service_class, resolve_month_end_trade_dates):
        resolve_month_end_trade_dates.return_value = [date(2025, 5, 30), date(2025, 6, 30)]
        job = SimpleNamespace(
            id=1356,
            plan_id=1346,
            data_type='industry_stocks',
            config={
                'symbols': ['801010'],
                'params': {
                    'start_date': '2025-05-01',
                    'end_date': '2025-06-30',
                },
            },
        )

        execute_collect(job)

        resolve_month_end_trade_dates.assert_called_once()
        service_class.return_value.collect_industry_stocks.assert_called_once_with(
            ['801010'],
            target_dates=[date(2025, 5, 30), date(2025, 6, 30)],
        )

    @patch('saa_collector.services.factory.provider_config.load_config')
    @patch('saa_collector.services.common.sw_industry_service.SwIndustryService')
    def test_execute_collect_rejects_unsupported_industry_stocks_provider(self, service_class, load_config):
        load_config.return_value = {
            'saa_collector': {
                'default_provider': 'tushare',
                'data_providers': {
                    'industry_stocks': 'akshare',
                },
            },
        }
        job = SimpleNamespace(
            id=1356,
            plan_id=1346,
            data_type='industry_stocks',
            config={
                'symbols': ['801010'],
                'params': {
                    'start_date': '2025-05-01',
                    'end_date': '2025-06-30',
                },
            },
        )

        with self.assertRaisesMessage(
                ValueError,
                'Unsupported collector provider for data_type=industry_stocks: provider=akshare supported=tushare'):
            execute_collect(job)

        service_class.assert_not_called()
