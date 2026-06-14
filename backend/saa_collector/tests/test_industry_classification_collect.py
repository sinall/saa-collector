from datetime import date
from unittest.mock import patch

from django.test import TestCase

from saa_collector.models import CollectJob
from saa_collector.services.collect_plan_executor import execute_collect


class CsrcIndustryClassificationCollectTest(TestCase):
    @patch('saa_collector.services.common.industry_classification_service.CsrcIndustryClassificationService')
    def test_execute_collect_runs_csrc_industry_classification_job(self, service_class):
        job = CollectJob.objects.create(
            data_type='csrc_industry_classifications',
            config={'symbols': [], 'params': {}},
        )

        execute_collect(job)

        service_class.return_value.collect.assert_called_once()

    @patch('saa_collector.services.collect_plan_executor.resolve_stock_status_target_dates')
    @patch('saa_collector.services.collect_plan_executor.resolve_index_constituent_payloads_by_dates')
    @patch('saa_collector.services.common.stock_status_service.StockStatusService')
    def test_execute_collect_runs_extras_job(self, service_class, resolve_index_payloads, resolve_target_dates):
        resolve_target_dates.return_value = [date(2026, 5, 29)]
        resolve_index_payloads.return_value = {
            date(2026, 5, 29): (date(2026, 5, 29), {'000001'}),
        }
        job = CollectJob.objects.create(
            data_type='extras',
            config={'symbols': [], 'params': {'start_date': '2026-05-29'}},
        )

        execute_collect(job)

        service_class.return_value.collect.assert_called_once_with(
            target_dates=[date(2026, 5, 29)],
            symbols=None,
        )

    @patch('saa_collector.services.common.index_quote_service.IndexQuoteService')
    def test_execute_collect_runs_index_quotes_job(self, service_class):
        job = CollectJob.objects.create(
            data_type='index_quotes',
            config={'symbols': ['000906.XSHG'], 'params': {'start_date': '2026-05-29'}},
        )

        execute_collect(job)

        service_class.return_value.collect.assert_called_once()

    @patch('saa_collector.services.collect_plan_executor.resolve_month_end_trade_dates')
    @patch('saa_collector.services.common.index_weight_service.IndexWeightService')
    def test_execute_collect_runs_index_weights_job(self, service_class, resolve_month_end_trade_dates):
        resolve_month_end_trade_dates.return_value = [date(2026, 5, 29)]
        job = CollectJob.objects.create(
            data_type='index_weights',
            config={'symbols': ['000906.XSHG'], 'params': {'start_date': '2026-05-29'}},
        )

        with self.assertLogs(level='INFO') as logs:
            execute_collect(job)

        resolve_month_end_trade_dates.assert_called_once()
        service_class.return_value.collect.assert_called_once_with(
            ['000906.XSHG'],
            trade_dates=[date(2026, 5, 29)],
        )
        self.assertTrue(
            any('Resolved index_weights trade dates:' in message for message in logs.output),
        )

    @patch('saa_collector.services.common.sw_industry_service.SwIndustryService')
    def test_execute_collect_runs_industries_job(self, service_class):
        job = CollectJob.objects.create(
            data_type='industries',
            config={'symbols': [], 'params': {'start_date': '2026-05-29'}},
        )

        execute_collect(job)

        service_class.return_value.collect_industries.assert_called_once()

    @patch('saa_collector.services.common.sw_industry_service.SwIndustryService')
    def test_execute_collect_runs_industry_stocks_job(self, service_class):
        job = CollectJob.objects.create(
            data_type='industry_stocks',
            config={'symbols': ['801010'], 'params': {'start_date': '2026-05-29'}},
        )

        execute_collect(job)

        service_class.return_value.collect_industry_stocks.assert_called_once()

    @patch('saa_collector.services.collect_plan_executor.resolve_month_end_trade_dates')
    @patch('saa_collector.services.common.index_weight_service.IndexWeightService')
    def test_execute_collect_routes_index_stock_scope_for_industry_stocks_to_index_weights(
            self, service_class, resolve_month_end_trade_dates):
        resolve_month_end_trade_dates.return_value = [date(2026, 5, 29), date(2026, 6, 13)]
        job = CollectJob.objects.create(
            data_type='industry_stocks',
            config={
                'symbols': [],
                'stock_scope': 'INDEX',
                'stock_list_code': '000906',
                'params': {'start_date': '2026-05-29', 'end_date': '2026-06-14'},
            },
        )

        execute_collect(job)

        service_class.return_value.collect.assert_called_once_with(
            ['000906'],
            trade_dates=[date(2026, 5, 29), date(2026, 6, 13)],
        )

    @patch('saa_collector.services.collect_plan_executor.resolve_index_scope_symbols_at')
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_execute_collect_resolves_index_stock_scope_to_symbols(self, factory_class, resolve_index_scope_symbols_at):
        resolve_index_scope_symbols_at.return_value = ['000001', '000002']
        job = CollectJob.objects.create(
            data_type='quote',
            config={
                'symbols': [],
                'stock_scope': 'INDEX',
                'stock_list_code': '000906',
                'params': {},
            },
        )

        execute_collect(job)

        resolve_index_scope_symbols_at.assert_called_once()
        factory_class.return_value.create_quote_service.return_value.collect.assert_called_once_with(
            ['000001', '000002']
        )

    @patch('saa_collector.services.collect_plan_executor.resolve_month_end_trade_dates')
    @patch('saa_collector.services.common.index_weight_service.IndexWeightService')
    def test_execute_collect_runs_index_weights_job_with_index_scope(
            self, service_class, resolve_month_end_trade_dates):
        resolve_month_end_trade_dates.return_value = [date(2026, 5, 29), date(2026, 6, 13)]
        job = CollectJob.objects.create(
            data_type='index_weights',
            config={
                'symbols': [],
                'stock_scope': 'INDEX',
                'stock_list_code': '000906',
                'params': {'start_date': '2026-05-29', 'end_date': '2026-06-14'},
            },
        )

        execute_collect(job)

        service_class.return_value.collect.assert_called_once_with(
            ['000906'],
            trade_dates=[date(2026, 5, 29), date(2026, 6, 13)],
        )

    @patch('saa_collector.services.collect_plan_executor.resolve_month_end_trade_dates')
    @patch('saa_collector.services.common.index_quote_service.IndexQuoteService')
    def test_execute_collect_keeps_daily_tasks_on_execution_day_path(
            self, service_class, resolve_month_end_trade_dates):
        job = CollectJob.objects.create(
            data_type='quote',
            config={'symbols': ['000906.XSHG'], 'params': {'start_date': '2026-05-29'}},
        )

        execute_collect(job)

        resolve_month_end_trade_dates.assert_not_called()
        service_class.return_value.collect.assert_called_once_with(['000906.XSHG'])
