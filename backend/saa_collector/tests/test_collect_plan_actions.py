from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from saa_collector.models import CollectJob, CollectPlan
from saa_collector.services.collect_plan_executor import execute_plan


class CollectPlanActionAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)

    @patch('saa_collector.task_dispatcher.current_app.control.revoke')
    def test_stop_plan_marks_unfinished_jobs_stopped(self, revoke):
        plan = CollectPlan.objects.create(
            name='停止测试',
            status='RUNNING',
            queue_task_id='task-1',
        )
        success_job = CollectJob.objects.create(
            plan=plan,
            data_type='quote',
            status='SUCCESS',
            config={'symbols': ['000001'], 'params': {}},
        )
        running_job = CollectJob.objects.create(
            plan=plan,
            data_type='quote',
            status='RUNNING',
            start_time=timezone.now(),
            config={'symbols': ['000002'], 'params': {}},
        )
        queued_job = CollectJob.objects.create(
            plan=plan,
            data_type='quote',
            status='QUEUED',
            config={'symbols': ['000003'], 'params': {}},
        )

        response = self.client.post(f'/api/collect-plans/{plan.id}/stop/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        plan.refresh_from_db()
        success_job.refresh_from_db()
        running_job.refresh_from_db()
        queued_job.refresh_from_db()
        self.assertEqual(plan.status, 'STOPPED')
        self.assertIsNone(plan.queue_task_id)
        self.assertEqual(success_job.status, 'SUCCESS')
        self.assertEqual(running_job.status, 'STOPPED')
        self.assertEqual(queued_job.status, 'STOPPED')
        revoke.assert_called_once_with('task-1', terminate=False)

    @patch('saa_collector.tasks.execute_collect_plan.delay')
    def test_continue_plan_queues_only_non_success_jobs(self, delay):
        delay.return_value.id = 'celery-task-1'
        plan = CollectPlan.objects.create(
            name='继续测试',
            status='STOPPED',
        )
        success_job = CollectJob.objects.create(
            plan=plan,
            data_type='quote',
            status='SUCCESS',
            config={'symbols': ['000001'], 'params': {}},
        )
        stopped_job = CollectJob.objects.create(
            plan=plan,
            data_type='quote',
            status='STOPPED',
            config={'symbols': ['000002'], 'params': {}},
        )
        failed_job = CollectJob.objects.create(
            plan=plan,
            data_type='quote',
            status='FAILED',
            config={'symbols': ['000003'], 'params': {}},
        )

        response = self.client.post(f'/api/collect-plans/{plan.id}/continue/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        plan.refresh_from_db()
        success_job.refresh_from_db()
        stopped_job.refresh_from_db()
        failed_job.refresh_from_db()
        self.assertEqual(plan.status, 'QUEUED')
        self.assertEqual(plan.queue_task_id, 'celery-task-1')
        self.assertEqual(success_job.status, 'SUCCESS')
        self.assertEqual(stopped_job.status, 'QUEUED')
        self.assertEqual(failed_job.status, 'QUEUED')
        delay.assert_called_once_with(plan.id)

    def test_reset_plan_clears_all_job_state(self):
        plan = CollectPlan.objects.create(
            name='重置测试',
            status='STOPPED',
            started_at=timezone.now(),
            completed_at=timezone.now(),
            queued_at=timezone.now(),
            queue_task_id='task-1',
        )
        CollectJob.objects.create(
            plan=plan,
            data_type='quote',
            status='SUCCESS',
            start_time=timezone.now(),
            end_time=timezone.now(),
            message='done',
            config={'symbols': ['000001'], 'params': {}, 'remaining_symbols': ['000001']},
        )
        CollectJob.objects.create(
            plan=plan,
            data_type='quote',
            status='STOPPED',
            start_time=timezone.now(),
            end_time=timezone.now(),
            message='stopped',
            config={'symbols': ['000002'], 'params': {}, 'failed_symbols': ['000002']},
        )

        response = self.client.post(f'/api/collect-plans/{plan.id}/reset/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'PENDING')
        self.assertIsNone(plan.started_at)
        self.assertIsNone(plan.completed_at)
        self.assertIsNone(plan.queued_at)
        self.assertIsNone(plan.queue_task_id)
        for job in plan.jobs.all():
            self.assertEqual(job.status, 'PENDING')
            self.assertIsNone(job.start_time)
            self.assertIsNone(job.end_time)
            self.assertIsNone(job.message)
            self.assertNotIn('remaining_symbols', job.config)
            self.assertNotIn('failed_symbols', job.config)


class CollectPlanResumeExecutionTest(TestCase):
    @patch('saa_collector.services.collect_plan_executor.execute_job')
    def test_execute_plan_skips_success_jobs(self, execute_job):
        plan = CollectPlan.objects.create(name='跳过成功任务')
        success_job = CollectJob.objects.create(
            plan=plan,
            data_type='quote',
            status='SUCCESS',
            config={'symbols': ['000001'], 'params': {}},
        )
        pending_job = CollectJob.objects.create(
            plan=plan,
            data_type='quote',
            status='PENDING',
            config={'symbols': ['000002'], 'params': {}},
        )

        execute_plan(plan.id, task_id='celery-task-1')

        execute_job.assert_called_once_with(pending_job.id, 'celery-task-1', plan.id)
        success_job.refresh_from_db()
        pending_job.refresh_from_db()
        plan.refresh_from_db()
        self.assertEqual(success_job.status, 'SUCCESS')
        self.assertEqual(pending_job.status, 'PENDING')
        self.assertEqual(plan.status, 'COMPLETED')
