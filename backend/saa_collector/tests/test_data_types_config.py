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
