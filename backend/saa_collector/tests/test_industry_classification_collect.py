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

    @patch('saa_collector.services.common.stock_status_service.StockStatusService')
    def test_execute_collect_runs_extras_job(self, service_class):
        job = CollectJob.objects.create(
            data_type='extras',
            config={'symbols': [], 'params': {'start_date': '2026-05-29'}},
        )

        execute_collect(job)

        service_class.return_value.collect.assert_called_once()

    @patch('saa_collector.services.common.index_quote_service.IndexQuoteService')
    def test_execute_collect_runs_index_quotes_job(self, service_class):
        job = CollectJob.objects.create(
            data_type='index_quotes',
            config={'symbols': ['000906.XSHG'], 'params': {'start_date': '2026-05-29'}},
        )

        execute_collect(job)

        service_class.return_value.collect.assert_called_once()

    @patch('saa_collector.services.common.index_weight_service.IndexWeightService')
    def test_execute_collect_runs_index_weights_job(self, service_class):
        job = CollectJob.objects.create(
            data_type='index_weights',
            config={'symbols': ['000906.XSHG'], 'params': {'start_date': '2026-05-29'}},
        )

        execute_collect(job)

        service_class.return_value.collect.assert_called_once()

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
