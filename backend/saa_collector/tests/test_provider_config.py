from django.test import SimpleTestCase, override_settings

from saa_collector.services.factory.provider_config import require_provider, resolve_provider


class ProviderConfigTest(SimpleTestCase):
    @override_settings(DATA_SOURCE='tushare')
    def test_resolve_provider_uses_data_type_override(self):
        selection = resolve_provider(
            'industry_stocks',
            config={
                'saa_collector': {
                    'default_provider': 'tushare',
                    'data_providers': {
                        'industry_stocks': 'akshare',
                    },
                },
            },
        )

        self.assertEqual(selection.provider, 'akshare')
        self.assertEqual(selection.source, 'data_providers.industry_stocks')

    @override_settings(DATA_SOURCE='akshare')
    def test_resolve_provider_falls_back_to_default_provider(self):
        selection = resolve_provider(
            'quote',
            config={
                'saa_collector': {
                    'default_provider': 'tushare',
                    'data_providers': {},
                },
            },
        )

        self.assertEqual(selection.provider, 'tushare')
        self.assertEqual(selection.source, 'default_provider')

    @override_settings(DATA_SOURCE='akshare')
    def test_resolve_provider_falls_back_to_settings(self):
        selection = resolve_provider('quote', config={})

        self.assertEqual(selection.provider, 'akshare')
        self.assertEqual(selection.source, 'settings.DATA_SOURCE')

    def test_require_provider_rejects_unsupported_data_type_override(self):
        with self.assertRaisesMessage(
                ValueError,
                'Unsupported collector provider for data_type=industry_stocks: provider=akshare supported=tushare'):
            require_provider(
                'industry_stocks',
                {'tushare'},
                config={
                    'saa_collector': {
                        'data_providers': {
                            'industry_stocks': 'akshare',
                        },
                    },
                },
            )

    def test_unknown_provider_is_rejected(self):
        with self.assertRaisesMessage(ValueError, 'Unsupported collector provider: unknown'):
            resolve_provider(
                'quote',
                config={
                    'saa_collector': {
                        'data_providers': {
                            'quote': 'unknown',
                        },
                    },
                },
            )
