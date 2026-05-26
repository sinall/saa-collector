import json

from django.test import TestCase
from django.utils import timezone

from saa_collector.models import ExternalApiCacheEntry
from saa_collector.third_party.api_cache import DjangoExternalApiCacheStore


class ExternalApiCacheStoreTest(TestCase):
    def test_set_records_stores_only_raw_response_body(self):
        store = DjangoExternalApiCacheStore()

        store.set_records(
            provider='tushare',
            api_name='balancesheet',
            cache_key='abc',
            canonical_call={'provider': 'tushare', 'api': 'balancesheet'},
            params={'ts_code': '000001.SZ'},
            fields='ts_code,end_date',
            response_records=[{'ts_code': '000001.SZ', 'end_date': '20231231'}],
            schema_version='tushare-raw-v1',
            ttl_seconds=60,
        )

        entry = ExternalApiCacheEntry.objects.get(cache_key='abc')
        self.assertEqual(entry.response_content_type, 'application/json')
        self.assertEqual(entry.response_encoding, 'utf-8')
        self.assertEqual(
            json.loads(entry.response_body.decode('utf-8')),
            [{'ts_code': '000001.SZ', 'end_date': '20231231'}],
        )
        self.assertFalse(hasattr(entry, 'response_json'))

    def test_get_records_decodes_json_from_raw_response_body(self):
        store = DjangoExternalApiCacheStore()
        ExternalApiCacheEntry.objects.create(
            provider='tushare',
            api_name='balancesheet',
            cache_key='abc',
            canonical_call_json={'provider': 'tushare', 'api': 'balancesheet'},
            params_json={'ts_code': '000001.SZ'},
            fields='ts_code,end_date',
            response_body=json.dumps(
                [{'ts_code': '000001.SZ', 'end_date': '20231231'}]
            ).encode('utf-8'),
            response_content_type='application/json',
            response_encoding='utf-8',
            response_sha256='unused',
            raw_response_schema_version='tushare-raw-v1',
            expires_at=timezone.now() + timezone.timedelta(seconds=60),
        )

        records = store.get_records(provider='tushare', api_name='balancesheet', cache_key='abc')

        self.assertEqual(records, [{'ts_code': '000001.SZ', 'end_date': '20231231'}])

    def test_set_response_and_get_response_round_trip_binary_body(self):
        store = DjangoExternalApiCacheStore()

        store.set_response(
            provider='cnindex',
            api_name='sylExcelDowload',
            cache_key='xls-key',
            canonical_call={'provider': 'cnindex', 'api': 'sylExcelDowload'},
            params={'checkDate': '2026-05-22', 'category': 'crsc_ch'},
            body=b'fake-xls-bytes',
            content_type='application/vnd.ms-excel;charset=UTF-8',
            filename='crsc_ch_2026-05-22.xls',
            status_code=200,
            headers={'Content-Type': 'application/vnd.ms-excel;charset=UTF-8'},
            schema_version='cnindex-raw-v1',
            ttl_seconds=60,
        )

        cached = store.get_response(provider='cnindex', api_name='sylExcelDowload', cache_key='xls-key')

        self.assertEqual(cached.body, b'fake-xls-bytes')
        self.assertEqual(cached.content_type, 'application/vnd.ms-excel;charset=UTF-8')
        self.assertEqual(cached.filename, 'crsc_ch_2026-05-22.xls')
        self.assertEqual(cached.status_code, 200)
        self.assertEqual(cached.headers['Content-Type'], 'application/vnd.ms-excel;charset=UTF-8')
