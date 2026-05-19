from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from saa_collector.third_party import tushare_api_client


class TushareApiClientTest(SimpleTestCase):
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
