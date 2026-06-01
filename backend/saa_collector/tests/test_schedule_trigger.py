from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from saa_collector.models import CollectSchedule


class CollectScheduleTriggerAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)

    @patch('saa_collector.views.dispatch_plan')
    def test_manual_trigger_returns_created_plan_for_requested_schedule(self, dispatch_plan):
        internal_schedule = CollectSchedule.objects.create(
            name='Tick数据采集',
            data_type='tick',
            symbols=[],
            params={},
            cron_expression='*/5 * * * *',
            status='ENABLED',
        )
        statement_schedule = CollectSchedule.objects.create(
            name='财务报表采集(5月)',
            data_type='financial_statements',
            symbols=[],
            params={},
            cron_expression='0 0 * * *',
            status='ENABLED',
        )

        response = self.client.post(f'/api/collect-schedules/{statement_schedule.id}/trigger/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        plan_data = response.data['data']['plan']
        self.assertIn('财务报表采集(5月)', plan_data['name'])
        self.assertEqual(plan_data['source_schedule_id'], statement_schedule.id)
        self.assertEqual(plan_data['source_schedule_name'], '财务报表采集(5月)')
        self.assertNotIn(internal_schedule.name, plan_data['name'])
        dispatch_plan.assert_called_once()

    def test_update_csrc_industry_classification_schedule(self):
        schedule = CollectSchedule.objects.create(
            name='证监会行业分类维护',
            data_type='csrc_industry_classifications',
            symbols=[],
            params={},
            cron_expression='5 0 7 5 *',
            status='DISABLED',
        )

        response = self.client.put(f'/api/collect-schedules/{schedule.id}/', {
            'name': '证监会行业分类维护',
            'data_type': 'csrc_industry_classifications',
            'symbols': [],
            'params': {},
            'cron_expression': '5 0 7 5 *',
            'status': 'DISABLED',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['data_type'], 'csrc_industry_classifications')
        self.assertEqual(response.data['data']['params'], {})

    def test_update_valuation_schedule(self):
        schedule = CollectSchedule.objects.create(
            name='估值数据采集',
            data_type='valuation',
            symbols=[],
            params={},
            cron_expression='30 19 * * 1-5',
            status='DISABLED',
        )

        response = self.client.put(f'/api/collect-schedules/{schedule.id}/', {
            'name': '估值数据采集',
            'data_type': 'valuation',
            'symbols': [],
            'params': {},
            'cron_expression': '30 19 * * 1-5',
            'status': 'DISABLED',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['data_type'], 'valuation')
        self.assertEqual(response.data['data']['params'], {})
