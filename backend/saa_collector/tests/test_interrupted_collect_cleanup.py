from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from saa_collector.models import CollectJob, CollectPlan


class InterruptedCollectCleanupTest(TestCase):
    def test_cleanup_marks_running_plan_failed_and_preserves_resume_progress(self):
        plan = CollectPlan.objects.create(
            name='财务报表采集',
            status='RUNNING',
            started_at=timezone.now(),
            queue_task_id='task-1',
        )
        job = CollectJob.objects.create(
            plan=plan,
            data_type='financial_statements',
            status='RUNNING',
            config={
                'symbols': ['000001', '000002'],
                'remaining_symbols': ['000002'],
                'params': {},
            },
        )

        call_command('cleanup_interrupted_collect_tasks')

        plan.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(plan.status, 'FAILED')
        self.assertIsNotNone(plan.completed_at)
        self.assertEqual(job.status, 'FAILED')
        self.assertIsNotNone(job.end_time)
        self.assertEqual(job.config['remaining_symbols'], ['000002'])


class EntrypointCleanupTest(TestCase):
    @patch.dict('os.environ', {
        'SERVICE': 'celery-worker',
        'COLLECTOR_CELERY_QUEUE': 'collector',
    }, clear=True)
    @patch('entrypoint.subprocess.run')
    def test_collector_worker_runs_cleanup_before_starting_celery(self, run):
        import entrypoint

        run.return_value.returncode = 0

        with self.assertRaises(SystemExit) as cm:
            entrypoint.main()

        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            run.call_args_list[0].args[0],
            ['python', 'manage.py', 'cleanup_interrupted_collect_tasks'],
        )
        self.assertEqual(run.call_args_list[1].args[0][:3], ['celery', '-A', 'config'])

    @patch.dict('os.environ', {
        'SERVICE': 'celery-worker',
        'COLLECTOR_CELERY_QUEUE': 'scheduler',
    }, clear=True)
    @patch('entrypoint.subprocess.run')
    def test_scheduler_worker_does_not_cleanup_collector_tasks(self, run):
        import entrypoint

        run.return_value.returncode = 0

        with self.assertRaises(SystemExit) as cm:
            entrypoint.main()

        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][:3], ['celery', '-A', 'config'])
