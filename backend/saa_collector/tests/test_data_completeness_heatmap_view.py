from unittest.mock import Mock, patch

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
        self.assertNotIn('trade_days', called_data_types)
        self.assertNotIn('stock_info', called_data_types)
        self.assertNotIn('securities', called_data_types)
        self.assertIn('historical_quote', called_data_types)
        self.assertIn('extras', called_data_types)
        messages = '\n'.join(logs.output)
        self.assertIn('heatmap request start frequency=monthly scope=all periods=1', messages)
        self.assertIn('heatmap request done frequency=monthly scope=all periods=1', messages)

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

    @patch('saa_collector.services.completeness_service.CompletenessService')
    def test_heatmap_returns_latest_cached_response_when_daily_cache_is_cold(self, service_class):
        cached_result = {
            'date_range': {'start': '2026-05', 'end': '2026-05'},
            'frequency': 'monthly',
            'periods': ['2026-05'],
            'data_types': [],
            'matrix': {},
            'scope': {'key': 'all', 'label': '全市场'},
        }
        cache.set('collector:heatmap:monthly:all:latest', cached_result, timeout=3600)

        response = self.client.get('/api/data-completeness/heatmap/?frequency=monthly')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['success'], True)
        self.assertEqual(response.data['data'], cached_result)
        service_class.assert_not_called()

    @patch('saa_collector.views.connection')
    @patch('saa_collector.services.completeness_service.CompletenessService')
    def test_heatmap_passes_index_scope_to_completeness_service(self, service_class, connection):
        cursor = Mock()
        cursor.fetchone.return_value = (800,)
        connection.cursor.return_value.__enter__.return_value = cursor

        service = service_class.return_value
        service.generate_periods.return_value = ['2026-05']
        service.calculate_all.return_value = {
            'date_range': {'start': '2026-05', 'end': '2026-05'},
            'frequency': 'monthly',
            'periods': ['2026-05'],
            'data_types': [],
            'matrix': {},
        }

        response = self.client.get('/api/data-completeness/heatmap/?frequency=monthly&scope=index:000906')

        self.assertEqual(response.status_code, 200)
        service_class.assert_called_once_with(stock_codes=None, index_code='000906')
        self.assertEqual(response.data['data']['scope']['key'], 'index:000906')
        self.assertEqual(response.data['data']['scope']['label'], '中证800')

    @patch('saa_collector.views.connection')
    def test_heatmap_rejects_unknown_scope(self, connection):
        cursor = Mock()
        cursor.fetchone.return_value = (0,)
        connection.cursor.return_value.__enter__.return_value = cursor

        response = self.client.get('/api/data-completeness/heatmap/?scope=index:missing')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['success'], False)

    @patch('saa_collector.views.connection')
    def test_heatmap_scopes_include_all_market_and_indexes(self, connection):
        cursor = Mock()
        cursor.fetchall.return_value = [('000906', '2026-05-29', 800)]
        connection.cursor.return_value.__enter__.return_value = cursor

        response = self.client.get('/api/data-completeness/heatmap/scopes/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['success'], True)
        self.assertEqual(response.data['data'][0], {
            'key': 'all',
            'label': '全市场',
            'type': 'all',
        })
        self.assertEqual(response.data['data'][1], {
            'key': 'index:000906',
            'label': '中证800',
            'type': 'index',
            'index': '000906',
            'latest_date': '2026-05-29',
            'constituent_count': 800,
        })

    @patch('saa_collector.views.connection')
    def test_heatmap_scope_symbols_resolve_latest_index_constituents(self, connection):
        cursor = Mock()
        cursor.fetchall.return_value = [
            ('000001', '2026-05-29'),
            ('600000', '2026-05-29'),
        ]
        connection.cursor.return_value.__enter__.return_value = cursor

        response = self.client.get('/api/data-completeness/heatmap/scope-symbols/?scope=index:000906')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['success'], True)
        self.assertEqual(response.data['data'], {
            'key': 'index:000906',
            'label': '中证800',
            'type': 'index',
            'index': '000906',
            'latest_date': '2026-05-29',
            'constituent_count': 2,
            'symbols': ['000001', '600000'],
        })
