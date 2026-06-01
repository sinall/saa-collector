from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient


class DataStatusViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)

    @patch('saa_collector.views.DATA_TYPE_CONFIG', new={
        'stock_info': {
            'table': 'saa_stocks',
            'label': '股票基本信息',
            'order': 1,
        },
        'industries': {
            'table': 'saa_industries',
            'label': '量化行业分类',
            'order': 2,
        },
        'valuation': {
            'table': None,
            'label': '估值数据',
            'order': 3,
        },
    })
    @patch('saa_collector.views.connection')
    def test_includes_table_backed_types_even_if_they_do_not_show_completeness(self, connection):
        cursor = Mock()
        cursor.fetchone.side_effect = [
            (5,),
            (2,),
        ]
        connection.cursor.return_value.__enter__.return_value = cursor

        response = self.client.get('/api/data-status/')

        self.assertEqual(response.status_code, 200)
        data_types = {
            item['data_type']: item
            for item in response.data['data']
        }

        self.assertIn('stock_info', data_types)
        self.assertIn('industries', data_types)
        self.assertNotIn('valuation', data_types)
        self.assertEqual(data_types['stock_info']['count'], 5)
        self.assertEqual(data_types['industries']['count'], 2)
