from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import pandas as pd
import numpy as np

from saa_collector.third_party import tushare_api_client


class TushareApiClientTest(TestCase):
    def tearDown(self):
        tushare_api_client._client = None

    @patch.dict(
        'os.environ',
        {'TUSHARE_RATE_LIMIT_REDIS_URL': 'redis://:pa@ss@example.redis.local:6380/2'},
    )
    @patch('saa_collector.third_party.tushare_api_client.ts.pro_api')
    def test_redis_rate_limiter_parses_password_with_at_sign(self, pro_api):
        redis_constructor = Mock()
        fake_redis = SimpleNamespace(Redis=redis_constructor)

        with patch.object(tushare_api_client, 'redis', fake_redis):
            tushare_api_client.TushareApiClient('token', rate_limit=60)

        pro_api.assert_called_once_with('token')
        redis_constructor.assert_called_once_with(
            host='example.redis.local',
            port=6380,
            db=2,
            password='pa@ss',
            socket_timeout=5,
            socket_connect_timeout=5,
        )

    @patch('saa_collector.third_party.tushare_api_client.ts.pro_api')
    @patch.object(tushare_api_client.TushareApiClient, '_build_redis_client', return_value=None)
    def test_local_rate_limiter_logs_wait_time(self, _build_redis_client, pro_api):
        client = tushare_api_client.TushareApiClient('token', rate_limit=60)
        client.interval = 1.0
        client.last_query_time = tushare_api_client.datetime.now()

        with patch('saa_collector.third_party.tushare_api_client.time.sleep') as sleep:
            with self.assertLogs(level='INFO') as logs:
                wait_seconds = client._wait_for_rate_limit()

        self.assertGreater(wait_seconds, 0)
        sleep.assert_called_once()
        self.assertIn('limiter=local', '\n'.join(logs.output))
        self.assertIn('wait_seconds=', '\n'.join(logs.output))

    @patch('saa_collector.third_party.tushare_api_client.ts.pro_api')
    @patch.object(tushare_api_client.TushareApiClient, '_build_redis_client')
    def test_global_rate_limiter_logs_wait_time(self, build_redis_client, pro_api):
        redis_client = Mock()
        redis_client.set.return_value = True
        redis_client.get.side_effect = [
            str(tushare_api_client.time.time()).encode(),
            b'lock-token',
        ]
        build_redis_client.return_value = redis_client

        client = tushare_api_client.TushareApiClient('token', rate_limit=60)
        client.interval = 1.0

        with patch('saa_collector.third_party.tushare_api_client.uuid.uuid4', return_value='lock-token'):
            with patch('saa_collector.third_party.tushare_api_client.time.sleep') as sleep:
                with self.assertLogs(level='INFO') as logs:
                    wait_seconds = client._wait_for_global_rate_limit()

        self.assertGreater(wait_seconds, 0)
        sleep.assert_called_once()
        self.assertIn('limiter=global', '\n'.join(logs.output))
        self.assertIn('wait_seconds=', '\n'.join(logs.output))

    @patch('saa_collector.third_party.tushare_api_client.ts.pro_api')
    @patch.object(tushare_api_client.TushareApiClient, '_build_redis_client', return_value=None)
    def test_cache_key_ignores_fields_and_normalizes_params(self, _build_redis_client, pro_api):
        client = tushare_api_client.TushareApiClient('token', rate_limit=60)

        first = client.build_cache_key(
            'balancesheet',
            fields='ts_code,end_date,total_assets',
            params={'ts_code': '000001.SZ', 'start_date': ''}
        )
        second = client.build_cache_key(
            'balancesheet',
            fields='ts_code,end_date',
            params={'start_date': None, 'ts_code': '000001.SZ'}
        )

        self.assertEqual(first, second)

    @patch('saa_collector.third_party.tushare_api_client.ts.pro_api')
    @patch.object(tushare_api_client.TushareApiClient, '_build_redis_client', return_value=None)
    def test_query_returns_cached_dataframe_without_upstream_call(self, _build_redis_client, pro_api):
        cache_store = Mock()
        cache_store.get.return_value = [
            {'ts_code': '000001.SZ', 'end_date': '20231231', 'total_assets': 1},
        ]
        client = tushare_api_client.TushareApiClient(
            'token',
            rate_limit=60,
            cache_store=cache_store,
        )

        result = client.query(
            'balancesheet',
            fields='ts_code,end_date',
            ts_code='000001.SZ',
            api_cache_enabled=True,
        )

        pro_api.return_value.query.assert_not_called()
        self.assertEqual(list(result.columns), ['ts_code', 'end_date'])
        self.assertEqual(result.to_dict('records'), [
            {'ts_code': '000001.SZ', 'end_date': '20231231'},
        ])
        cache_store.get.assert_called_once()

    @patch('saa_collector.third_party.tushare_api_client.ts.pro_api')
    @patch.object(tushare_api_client.TushareApiClient, '_build_redis_client', return_value=None)
    def test_query_cache_hit_skips_rate_limit_wait(self, _build_redis_client, pro_api):
        cache_store = Mock()
        cache_store.get.return_value = [
            {'ts_code': '000001.SZ', 'end_date': '20231231'},
        ]
        client = tushare_api_client.TushareApiClient(
            'token',
            rate_limit=60,
            cache_store=cache_store,
        )

        with patch.object(client, '_wait_for_rate_limit') as wait_for_rate_limit:
            client.query(
                'balancesheet',
                fields='ts_code,end_date',
                ts_code='000001.SZ',
                api_cache_enabled=True,
            )

        wait_for_rate_limit.assert_not_called()
        pro_api.return_value.query.assert_not_called()

    @patch('saa_collector.third_party.tushare_api_client.ts.pro_api')
    @patch.object(tushare_api_client.TushareApiClient, '_build_redis_client', return_value=None)
    def test_query_cache_hit_does_not_update_last_query_time(self, _build_redis_client, pro_api):
        cache_store = Mock()
        cache_store.get.return_value = [
            {'ts_code': '000001.SZ', 'end_date': '20231231'},
        ]
        client = tushare_api_client.TushareApiClient(
            'token',
            rate_limit=60,
            cache_store=cache_store,
        )
        original_last_query_time = client.last_query_time

        client.query(
            'balancesheet',
            fields='ts_code,end_date',
            ts_code='000001.SZ',
            api_cache_enabled=True,
        )

        self.assertEqual(client.last_query_time, original_last_query_time)
        pro_api.return_value.query.assert_not_called()

    @patch('saa_collector.third_party.tushare_api_client.ts.pro_api')
    @patch.object(tushare_api_client.TushareApiClient, '_build_redis_client', return_value=None)
    def test_query_misses_cache_when_cached_fields_do_not_cover_request(self, _build_redis_client, pro_api):
        cache_store = Mock()
        cache_store.get.return_value = [
            {'ts_code': '000001.SZ', 'end_date': '20231231'},
        ]
        pro_api.return_value.query.return_value = pd.DataFrame([
            {'ts_code': '000001.SZ', 'end_date': '20231231', 'total_assets': 1},
        ])
        client = tushare_api_client.TushareApiClient(
            'token',
            rate_limit=60,
            cache_store=cache_store,
        )

        result = client.query(
            'balancesheet',
            fields='ts_code,end_date,total_assets',
            ts_code='000001.SZ',
            api_cache_enabled=True,
        )

        pro_api.return_value.query.assert_called_once()
        cache_store.set.assert_called_once()
        self.assertEqual(list(result.columns), ['ts_code', 'end_date', 'total_assets'])

    @patch('saa_collector.third_party.tushare_api_client.ts.pro_api')
    @patch.object(tushare_api_client.TushareApiClient, '_build_redis_client', return_value=None)
    def test_query_sanitizes_cached_response_records_for_mysql_json(self, _build_redis_client, pro_api):
        cache_store = Mock()
        cache_store.get.return_value = None
        pro_api.return_value.query.return_value = pd.DataFrame([
            {
                'ts_code': '000001.SZ',
                'cash_div_tax': np.nan,
                'ex_date': pd.NaT,
                'base_share': np.inf,
            },
        ])
        client = tushare_api_client.TushareApiClient(
            'token',
            rate_limit=60,
            cache_store=cache_store,
        )

        client.query(
            'dividend',
            fields='ts_code,cash_div_tax,ex_date,base_share',
            ts_code='000001.SZ',
            api_cache_enabled=True,
        )

        cache_store.set.assert_called_once()
        response_records = cache_store.set.call_args.kwargs['response_records']
        self.assertEqual(response_records, [
            {
                'ts_code': '000001.SZ',
                'cash_div_tax': None,
                'ex_date': None,
                'base_share': None,
            },
        ])

    @patch('saa_collector.third_party.tushare_api_client.ts.pro_api')
    @patch.object(tushare_api_client.TushareApiClient, '_build_redis_client', return_value=None)
    def test_query_bypasses_cache_when_requested(self, _build_redis_client, pro_api):
        cache_store = Mock()
        pro_api.return_value.query.return_value = pd.DataFrame([
            {'ts_code': '000001.SZ'},
        ])
        client = tushare_api_client.TushareApiClient(
            'token',
            rate_limit=60,
            cache_store=cache_store,
        )

        client.query(
            'balancesheet',
            fields='ts_code',
            ts_code='000001.SZ',
            api_cache_enabled=True,
            api_cache_bypass=True,
        )

        cache_store.get.assert_not_called()
        cache_store.set.assert_not_called()
        pro_api.return_value.query.assert_called_once()

    @patch('saa_collector.third_party.tushare_api_client.ts.pro_api')
    @patch.object(tushare_api_client.TushareApiClient, '_build_redis_client', return_value=None)
    def test_query_does_not_cache_uncacheable_api_by_default(self, _build_redis_client, pro_api):
        cache_store = Mock()
        pro_api.return_value.query.return_value = pd.DataFrame([
            {'ts_code': '000001.SZ'},
        ])
        client = tushare_api_client.TushareApiClient(
            'token',
            rate_limit=60,
            cache_store=cache_store,
        )

        client.query(
            'daily',
            fields='ts_code',
            ts_code='000001.SZ',
            api_cache_enabled=True,
        )

        cache_store.get.assert_not_called()
        cache_store.set.assert_not_called()
        pro_api.return_value.query.assert_called_once()

    @patch('saa_collector.third_party.tushare_api_client.ts.pro_api')
    @patch.object(tushare_api_client.TushareApiClient, '_build_redis_client', return_value=None)
    def test_query_caches_sw_industry_apis_by_default(self, _build_redis_client, pro_api):
        cache_store = Mock()
        cache_store.get.return_value = None
        pro_api.return_value.query.return_value = pd.DataFrame([
            {'index_code': '801010.SI', 'industry_name': '农林牧渔'},
        ])
        client = tushare_api_client.TushareApiClient(
            'token',
            rate_limit=60,
            cache_store=cache_store,
        )

        client.query(
            'index_classify',
            level='L1',
            src='SW2021',
            api_cache_enabled=True,
        )

        cache_store.get.assert_called_once()
        cache_store.set.assert_called_once()
        self.assertEqual(cache_store.set.call_args.kwargs['ttl_seconds'], 7 * 24 * 60 * 60)

        cache_store.reset_mock()
        cache_store.get.return_value = None
        pro_api.return_value.query.return_value = pd.DataFrame([
            {'l1_code': '801010.SI', 'ts_code': '000001.SZ'},
        ])

        client.query(
            'index_member_all',
            l1_code='801010.SI',
            is_new='Y',
            api_cache_enabled=True,
        )

        cache_store.get.assert_called_once()
        cache_store.set.assert_called_once()
        self.assertEqual(cache_store.set.call_args.kwargs['ttl_seconds'], 24 * 60 * 60)
