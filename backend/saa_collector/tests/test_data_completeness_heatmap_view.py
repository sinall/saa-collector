from unittest.mock import patch

from django.core.cache import cache
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient


class DataCompletenessHeatmapViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)

    @patch('saa_collector.services.completeness_service.CompletenessService')
    def test_heatmap_excludes_internal_data_types(self, service_class):
        service = service_class.return_value
        service.generate_periods.return_value = ['2026-05']
        service.calculate_all.return_value = {
            'date_range': {'start': '2026-05', 'end': '2026-05'},
            'frequency': 'monthly',
            'periods': ['2026-05'],
            'data_types': [],
            'matrix': {},
        }

        with self.assertLogs('saa_collector.views', level='INFO') as logs:
            response = self.client.get('/api/data-completeness/heatmap/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['success'], True)
        called_data_types = service.calculate_all.call_args.args[0]
        self.assertNotIn('tick', called_data_types)
        self.assertIn('trade_days', called_data_types)
        messages = '\n'.join(logs.output)
        self.assertIn('heatmap request start frequency=monthly periods=1', messages)
        self.assertIn('heatmap request done frequency=monthly periods=1', messages)

    @patch('saa_collector.services.completeness_service.CompletenessService')
    def test_heatmap_reuses_cached_response_for_same_frequency(self, service_class):
        service = service_class.return_value
        service.generate_periods.return_value = ['2026-05']
        service.calculate_all.return_value = {
            'date_range': {'start': '2026-05', 'end': '2026-05'},
            'frequency': 'monthly',
            'periods': ['2026-05'],
            'data_types': [],
            'matrix': {},
        }

        first = self.client.get('/api/data-completeness/heatmap/?frequency=monthly')
        second = self.client.get('/api/data-completeness/heatmap/?frequency=monthly')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        service.calculate_all.assert_called_once()
