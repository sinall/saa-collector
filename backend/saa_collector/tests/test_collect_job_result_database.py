"""Run using explicitly isolated Django test settings, never production settings."""
from django.test import TestCase

from saa_collector.models import CollectJob
from saa_collector.serializers import CollectJobSerializer, CollectJobDetailSerializer
from saa_collector.services.collect_job_result import record_issue
from saa_collector.services.collect_plan_executor import (
    initialize_symbol_progress, mark_symbol_failure, mark_symbol_success,
)


class JobResultDatabaseTest(TestCase):
    def test_detail_only_and_read_only(self):
        job = CollectJob.objects.create(data_type='financial_statements')
        self.assertEqual(job.result, {})
        self.assertNotIn('result', CollectJobSerializer(job).data)
        self.assertEqual(CollectJobDetailSerializer(job).data['result'], {})
        serializer = CollectJobDetailSerializer(job, data={'result': {'forged': True}}, partial=True)
        self.assertTrue(serializer.is_valid())
        self.assertNotIn('result', serializer.validated_data)

    def test_all_scope_progress_retries_preserve_evidence_and_counts(self):
        job = CollectJob.objects.create(data_type='financial_statements', config={'symbols': []})
        initialize_symbol_progress(job.pk, ['600036', '600000'])
        record_issue(job.pk, {'code': 'SOURCE_FAILURE', 'symbol': '600036'})
        mark_symbol_failure(job.pk, '600036')
        mark_symbol_success(job.pk, '600000')
        mark_symbol_success(job.pk, '600000')
        job.refresh_from_db()
        self.assertEqual(job.result['summary'], dict(total_symbols=2, succeeded_symbols=1, failed_symbols=1))
        self.assertEqual(initialize_symbol_progress(job.pk, ['600036', '600000']), ['600036'])
        mark_symbol_success(job.pk, '600036')
        job.refresh_from_db()
        self.assertEqual(job.result['summary']['succeeded_symbols'], 2)
        self.assertEqual(job.result['summary']['failed_symbols'], 0)
        self.assertIsNotNone(job.result['issues'][0]['resolved_at'])
        self.assertEqual(job.message, '完成2只，失败0只')

    def test_task_issue_recording_failure_propagates(self):
        with self.assertRaises(CollectJob.DoesNotExist):
            record_issue(99999, {'code': 'SOURCE_FAILURE', 'symbol': '600036'})
