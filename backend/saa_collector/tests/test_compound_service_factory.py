from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory


class CompoundServiceFactoryTest(SimpleTestCase):
    @override_settings(DATA_SOURCE='tushare')
    @patch('saa_collector.services.factory.compound_service_factory.logger')
    def test_initialization_logs_selected_tushare_factory(self, logger_mock):
        factory = CompoundServiceFactory()

        self.assertEqual(factory.impl.__class__.__name__, 'TushareServiceFactoryImpl')
        logger_mock.info.assert_called_once_with(
            'CompoundServiceFactory initialized: data_type=%s provider=%s source=%s selected_impl=%s',
            None,
            'tushare',
            'settings.DATA_SOURCE',
            'TushareServiceFactoryImpl',
        )

    @override_settings(DATA_SOURCE='akshare')
    @patch('saa_collector.services.factory.compound_service_factory.logger')
    def test_initialization_logs_selected_akshare_factory(self, logger_mock):
        factory = CompoundServiceFactory()

        self.assertEqual(factory.impl.__class__.__name__, 'AkshareServiceFactoryImpl')
        logger_mock.info.assert_called_once_with(
            'CompoundServiceFactory initialized: data_type=%s provider=%s source=%s selected_impl=%s',
            None,
            'akshare',
            'settings.DATA_SOURCE',
            'AkshareServiceFactoryImpl',
        )

    @override_settings(DATA_SOURCE='tushare')
    @patch('saa_collector.services.factory.provider_config.load_config')
    @patch('saa_collector.services.factory.compound_service_factory.logger')
    def test_data_type_provider_override_selects_akshare_factory(self, logger_mock, load_config):
        load_config.return_value = {
            'saa_collector': {
                'default_provider': 'tushare',
                'data_providers': {
                    'quote': 'akshare',
                },
            },
        }

        factory = CompoundServiceFactory(data_type='quote')

        self.assertEqual(factory.impl.__class__.__name__, 'AkshareServiceFactoryImpl')
        logger_mock.info.assert_called_once_with(
            'CompoundServiceFactory initialized: data_type=%s provider=%s source=%s selected_impl=%s',
            'quote',
            'akshare',
            'data_providers.quote',
            'AkshareServiceFactoryImpl',
        )

    def test_explicit_unknown_provider_is_rejected(self):
        with self.assertRaisesMessage(ValueError, 'Unsupported collector provider: unknown'):
            CompoundServiceFactory(provider='unknown')
