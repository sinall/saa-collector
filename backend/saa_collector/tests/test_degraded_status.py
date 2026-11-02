from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from saa_collector.models import CollectJob, CollectPlan
from saa_collector.services.collect_job_result import merge_issue, resolve_symbol


class DegradedStatusTest(TestCase):
    def test_completed_symbols_stay_completed_before_terminal_status(self):
        from saa_collector.services.collect_plan_executor import (
            initialize_symbol_progress, mark_symbol_success,
            execute_resumable_symbol_loop,
        )
        job = CollectJob.objects.create(
            data_type='financial_statements', status='RUNNING',
            config={'symbols': ['600036']},
        )
        self.assertEqual(initialize_symbol_progress(job.id, ['600036']), ['600036'])
        mark_symbol_success(job.id, '600036')
        job.refresh_from_db()
        self.assertEqual(job.config.get('remaining_symbols'), [])
        for _ in range(2):
            with patch('builtins.print') as collect:
                execute_resumable_symbol_loop(job, ['600036'], collect)
                collect.assert_not_called()
            job.refresh_from_db()
            self.assertEqual(job.config.get('remaining_symbols'), [])

    def test_success_with_open_field_issue_is_degraded(self):
        result = merge_issue({}, dict(code='STATEMENT_FIELD_NULLIFIED', symbol='600036',
                                     action='STORE_NULL_CONTINUE'), 'now')
        job = CollectJob.objects.create(data_type='financial_statements', result=result)
        job.complete()
        job.refresh_from_db()
        self.assertEqual(job.status, 'DEGRADED')
        job.complete(success=False)
        self.assertEqual(job.status, 'FAILED')

    def test_success_without_issues_stays_success(self):
        job = CollectJob.objects.create(data_type='financial_statements')
        job.complete()
        self.assertEqual(job.status, 'SUCCESS')

    def test_truncated_warning_is_not_silently_successful(self):
        result = merge_issue({}, dict(code='STATEMENT_FIELD_NULLIFIED', symbol='600036',
                                     action='STORE_NULL_CONTINUE'), 'now', max_issues=0)
        job = CollectJob.objects.create(data_type='financial_statements', result=result)
        job.complete()
        self.assertEqual(job.status, 'DEGRADED')

    def test_symbol_success_does_not_resolve_field_quality(self):
        result = merge_issue({}, dict(code='STATEMENT_FIELD_NULLIFIED', symbol='600036',
                                     action='STORE_NULL_CONTINUE'), 'now')
        self.assertIsNone(resolve_symbol(result, '600036', 'later')['issues'][0]['resolved_at'])

    def test_plan_aggregates_failed_before_degraded(self):
        plan = CollectPlan.objects.create(name='quality')
        job = CollectJob.objects.create(plan=plan, data_type='financial_statements', status='DEGRADED')
        self.assertEqual(plan.finished_status(), 'DEGRADED')
        job.status = 'FAILED'
        job.save()
        self.assertEqual(plan.finished_status(), 'FAILED')

    @patch('saa_collector.tasks.execute_collect_plan.delay')
    def test_continue_does_not_requeue_degraded_job(self, delay):
        delay.return_value.id = 'test'
        user = User.objects.create_user(username='quality')
        client = APIClient()
        client.force_authenticate(user=user)
        plan = CollectPlan.objects.create(name='resume', status='STOPPED')
        job = CollectJob.objects.create(plan=plan, data_type='financial_statements', status='DEGRADED')
        response = client.post(f'/api/collect-plans/{plan.id}/continue/')
        self.assertEqual(response.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.status, 'DEGRADED')
