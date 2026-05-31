from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient


class TypeBrowseDataViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)

    @patch('saa_collector.views.connection')
    def test_index_weights_browse_filters_by_index_code_and_joins_stock_name(self, connection):
        cursor = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = [1]
        cursor.fetchall.return_value = [
            ('000906.XSHG', date(2026, 5, 29), '300308', '中际旭创', '中际旭创', 3.464),
        ]
        cursor.description = [
            ('index',),
            ('date',),
            ('code',),
            ('display_name',),
            ('stock_name',),
            ('weight',),
        ]

        response = self.client.get('/api/type-browse-data/saa_index_weights/', {
            'keyword': '000906',
            'page': 1,
            'page_size': 20,
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['total'], 1)
        self.assertEqual(response.data['data']['results'][0]['stock_name'], '中际旭创')

        sql = connection.cursor.return_value.__enter__.return_value.execute.call_args_list[1].args[0]
        self.assertIn('LEFT JOIN saa_stocks s ON t.code = s.symbol', sql)
        self.assertIn('t.`index` LIKE %s', sql)

    @patch('saa_collector.views.connection')
    def test_industry_stocks_browse_filters_by_industry_code_and_joins_stock_name(self, connection):
        cursor = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = [1]
        cursor.fetchall.return_value = [
            ('801010', date(2026, 5, 30), '000505', '股票A',),
        ]
        cursor.description = [
            ('industry_code',),
            ('date',),
            ('code',),
            ('stock_name',),
        ]

        response = self.client.get('/api/type-browse-data/saa_industry_stocks/', {
            'keyword': '801010',
            'page': 1,
            'page_size': 20,
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['total'], 1)
        self.assertEqual(response.data['data']['results'][0]['stock_name'], '股票A')

        sql = connection.cursor.return_value.__enter__.return_value.execute.call_args_list[1].args[0]
        self.assertIn('LEFT JOIN saa_stocks s ON t.code = s.symbol', sql)
        self.assertIn('t.industry_code LIKE %s', sql)
