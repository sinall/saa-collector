import json
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User


class InstantCollectAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)

    def test_create_plan_with_single_job(self):
        """Test creating a plan with a single collection job"""
        response = self.client.post('/api/collect-plans/', {
            'name': '即时采集-测试',
            'execution_mode': 'PARALLEL',
            'jobs': [{
                'data_type': 'quote',
                'symbols': ['000001', '000002'],
                'start_date': '2024-01-01',
                'end_date': '2024-12-31'
            }]
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['name'], '即时采集-测试')
        self.assertEqual(len(response.data['data']['jobs']), 1)
        self.assertEqual(response.data['data']['jobs'][0]['data_type'], 'quote')

    def test_create_plan_without_jobs(self):
        """Test creating a plan without jobs (backward compatibility)"""
        response = self.client.post('/api/collect-plans/', {
            'name': '空计划',
            'execution_mode': 'PARALLEL'
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['name'], '空计划')
        self.assertEqual(len(response.data['data']['jobs']), 0)
