from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient


class IntegrityReportVisibilityFilterTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)

    def test_create_report_rejects_internal_only_selection(self):
        response = self.client.post('/api/integrity-reports/', {
            'name': 'tick report',
            'stock_scope': 'ALL',
            'stock_codes': [],
            'data_types': ['tick'],
            'frequency': 'monthly',
            'date_start': '2026-05-01',
            'date_end': '2026-05-31',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('data_types', response.data['error'])
