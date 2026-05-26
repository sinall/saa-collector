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
