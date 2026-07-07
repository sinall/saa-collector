from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient


class DisplayFieldConfigViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)

    @patch('saa_collector.views.connection')
    def test_price_adjust_factor_has_default_display_config(self, connection):
        cursor = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = None

        response = self.client.get('/api/display-field-config/', {
            'table': 'saa_price_adjust_factors',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['table_label'], '复权因子')
        fields = response.data['data']['config']['fields']
        self.assertEqual([field['name'] for field in fields], ['code', 'date', 'adj_factor'])

