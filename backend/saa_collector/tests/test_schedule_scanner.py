from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient
from django.contrib.auth.models import User

from saa_collector.models import CollectPlan, CollectSchedule
from saa_collector.tasks import scan_due_collect_schedules


class ScheduleScannerTest(TestCase):
    def test_beat_scanner_uses_scheduler_queue(self):
        self.assertEqual(
            settings.CELERY_BEAT_SCHEDULE['scan-due-collect-schedules']['options']['queue'],
            'scheduler'
        )
        self.assertEqual(
            settings.CELERY_TASK_ROUTES['saa_collector.scan_due_collect_schedules']['queue'],
            'scheduler'
        )
        self.assertEqual(
            settings.CELERY_TASK_ROUTES['saa_collector.execute_collect_plan']['queue'],
            'collector'
        )

    @patch('saa_collector.task_dispatcher.dispatch_plan')
    def test_scan_initializes_next_trigger_without_immediate_dispatch(self, dispatch_plan):
        schedule = CollectSchedule.objects.create(
            name='Every five minutes',
            data_type='quote',
            symbols=['000001'],
            params={},
            cron_expression='*/5 * * * *',
            status='ENABLED',
        )

        result = scan_due_collect_schedules()

        schedule.refresh_from_db()
        self.assertEqual(result['initialized'], 1)
        self.assertEqual(result['created'], 0)
        self.assertIsNotNone(schedule.next_trigger_at)
        self.assertIsNone(schedule.last_triggered_at)
        self.assertFalse(dispatch_plan.called)

    @patch('saa_collector.task_dispatcher.dispatch_plan')
    def test_scan_creates_one_plan_for_due_schedule_and_advances_next_trigger(self, dispatch_plan):
        due_at = timezone.now() - timedelta(minutes=1)
        schedule = CollectSchedule.objects.create(
            name='Due schedule',
            data_type='quote',
            symbols=['000001'],
            params={'start_date': 'today'},
            cron_expression='*/5 * * * *',
            status='ENABLED',
            next_trigger_at=due_at,
        )

        result = scan_due_collect_schedules()

        schedule.refresh_from_db()
        self.assertEqual(result['created'], 1)
        self.assertEqual(CollectPlan.objects.count(), 1)
        plan = CollectPlan.objects.get()
        self.assertEqual(plan.source, 'SCHEDULE')
        self.assertEqual(plan.trigger_type, 'AUTO')
        self.assertEqual(plan.source_schedule_id, schedule.id)
        self.assertEqual(schedule.last_triggered_at, due_at)
        self.assertGreater(schedule.next_trigger_at, due_at)
        dispatch_plan.assert_called_once_with(plan)

        second_result = scan_due_collect_schedules()

        self.assertEqual(second_result['created'], 0)
        self.assertEqual(CollectPlan.objects.count(), 1)


class CollectScheduleAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)

    def test_create_enabled_schedule_sets_next_trigger_for_beat_scanner(self):
        response = self.client.post('/api/collect-schedules/', {
            'name': 'Beat scanner schedule',
            'data_type': 'quote',
            'symbols': ['000001'],
            'params': {},
            'cron_expression': '*/5 * * * *',
            'status': 'ENABLED',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['success'])
        schedule = CollectSchedule.objects.get()
        self.assertIsNotNone(schedule.next_trigger_at)

    def test_disabling_schedule_clears_next_trigger(self):
        schedule = CollectSchedule.objects.create(
            name='Enabled schedule',
            data_type='quote',
            symbols=['000001'],
            params={},
            cron_expression='*/5 * * * *',
            status='ENABLED',
            next_trigger_at=timezone.now(),
        )

        response = self.client.put(f'/api/collect-schedules/{schedule.id}/', {
            'status': 'DISABLED',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        schedule.refresh_from_db()
        self.assertIsNone(schedule.next_trigger_at)
