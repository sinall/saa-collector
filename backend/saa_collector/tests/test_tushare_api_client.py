from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from saa_collector.third_party import tushare_api_client


class TushareApiClientTest(TestCase):
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
