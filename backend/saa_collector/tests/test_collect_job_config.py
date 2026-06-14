from unittest import TestCase

from saa_collector.collect_job_config import build_collect_job_config, get_cache_control


class CollectJobConfigTest(TestCase):
    def test_build_collect_job_config_enables_api_cache_by_default(self):
        config = build_collect_job_config(symbols=['000001'], params={})

        self.assertEqual(config['symbols'], ['000001'])
        self.assertEqual(config['params'], {})
        self.assertIs(config['api_cache_enabled'], True)

    def test_build_collect_job_config_allows_params_to_disable_or_bypass_cache(self):
        config = build_collect_job_config(
            symbols=[],
            params={
                'api_cache_enabled': False,
                'api_cache_bypass': True,
                'api_cache_ttl_seconds': 60,
            },
        )

        self.assertIs(config['api_cache_enabled'], False)
        self.assertIs(config['api_cache_bypass'], True)
        self.assertEqual(config['api_cache_ttl_seconds'], 60)

    def test_build_collect_job_config_applies_default_date_anchor_from_data_type(self):
        config = build_collect_job_config(
            symbols=[],
            params={},
            data_type='index_weights',
        )

        self.assertEqual(config['date_anchor'], 'month_end_trade_day')

    def test_get_cache_control_prefers_top_level_config_over_params(self):
        config = {
            'api_cache_enabled': True,
            'params': {'api_cache_enabled': False},
        }

        self.assertIs(get_cache_control(config, 'api_cache_enabled'), True)

    def test_get_cache_control_reads_nested_params_when_top_level_missing(self):
        config = {
            'params': {'api_cache_enabled': True},
        }

        self.assertIs(get_cache_control(config, 'api_cache_enabled'), True)
