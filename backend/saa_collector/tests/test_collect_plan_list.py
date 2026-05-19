from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from saa_collector.models import CollectPlan


class CollectPlanListAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)

    def test_filters_collect_plans_by_source_status_and_trigger_type(self):
        CollectPlan.objects.create(
            name='Tick数据采集',
            source='SCHEDULE',
            trigger_type='AUTO',
            status='QUEUED',
        )
        expected = CollectPlan.objects.create(
            name='财务报表采集(5月)',
            source='SCHEDULE',
            trigger_type='MANUAL',
            status='FAILED',
        )
        CollectPlan.objects.create(
            name='即时采集',
            source='MANUAL',
            status='FAILED',
        )

        response = self.client.get('/api/collect-plans/', {
            'source': 'SCHEDULE',
            'trigger_type': 'MANUAL',
            'status': 'FAILED',
            'page_size': 20,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], expected.id)
        self.assertEqual(response.data['results'][0]['name'], '财务报表采集(5月)')
