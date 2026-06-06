from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient


class DataTypesConfigTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)

    def test_industry_data_types_are_named_by_usage(self):
        response = self.client.get('/api/data-types/')

        self.assertEqual(response.status_code, 200)
        data_types = {
            item['key']: item
            for item in response.data['data_types']
        }
        self.assertEqual(data_types['industries']['label'], '量化行业分类')
        self.assertEqual(data_types['industry_stocks']['label'], '行业成分股')
        self.assertEqual(data_types['csrc_industry_classifications']['label'], '证监会行业分类')
        self.assertEqual(data_types['csrc_industry_classifications']['table'], 'saa_industry_classifications')
        self.assertFalse(data_types['csrc_industry_classifications']['need_date'])

    def test_extras_data_type_is_available_for_mfactor_stock_status(self):
        response = self.client.get('/api/data-types/')

        self.assertEqual(response.status_code, 200)
        data_types = {
            item['key']: item
            for item in response.data['data_types']
        }
        self.assertEqual(data_types['extras']['label'], '股票状态')
        self.assertEqual(data_types['extras']['table'], 'saa_extras')
        self.assertEqual(data_types['extras']['stock_column'], 'code')
        self.assertEqual(data_types['extras']['frequency'], 'daily')
        self.assertEqual(data_types['extras']['completeness_model'], 'trading_day_security')
        self.assertTrue(data_types['extras']['need_date'])

    def test_securities_data_type_exposes_security_master_refresh(self):
        response = self.client.get('/api/data-types/')

        self.assertEqual(response.status_code, 200)
        data_types = {
            item['key']: item
            for item in response.data['data_types']
        }
        self.assertEqual(data_types['securities']['label'], '证券主数据')
        self.assertEqual(data_types['securities']['table'], 'saa_securities')
        self.assertEqual(data_types['securities']['stock_column'], 'code')
        self.assertFalse(data_types['securities']['need_date'])
        self.assertFalse(data_types['securities']['show_completeness'])

    def test_index_quotes_data_type_is_available_for_mfactor_benchmark_quotes(self):
        response = self.client.get('/api/data-types/')

        self.assertEqual(response.status_code, 200)
        data_types = {
            item['key']: item
            for item in response.data['data_types']
        }
        self.assertEqual(data_types['index_quotes']['label'], '指数行情')
        self.assertEqual(data_types['index_quotes']['table'], 'saa_index_quotes')
        self.assertFalse(data_types['index_quotes']['stock_level'])
        self.assertTrue(data_types['index_quotes']['need_date'])

    def test_completeness_model_is_exposed_for_heatmap_semantics(self):
        response = self.client.get('/api/data-types/')

        self.assertEqual(response.status_code, 200)
        data_types = {
            item['key']: item
            for item in response.data['data_types']
        }
        self.assertEqual(data_types['trade_days']['completeness_model'], 'calendar')
        self.assertEqual(data_types['stock_info']['completeness_model'], 'snapshot_security')
        self.assertEqual(data_types['balance_sheet']['completeness_model'], 'periodic_security')
        self.assertEqual(data_types['dividend']['completeness_model'], 'event_security')

    def test_internal_data_type_visibility_is_context_driven(self):
        response = self.client.get('/api/data-types/')

        self.assertEqual(response.status_code, 200)
        data_types = {
            item['key']: item
            for item in response.data['data_types']
        }
        self.assertIn('tick', data_types)
        self.assertIn('visibility', data_types['tick'])
        self.assertFalse(data_types['tick']['visibility']['integrity_report'])
        self.assertFalse(data_types['tick']['visibility']['collect'])
        self.assertTrue(data_types['tick']['visibility']['schedule'])
