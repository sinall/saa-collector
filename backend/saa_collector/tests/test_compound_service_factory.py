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
            'CompoundServiceFactory initialized: DATA_SOURCE=%s selected_impl=%s',
            'tushare',
            'TushareServiceFactoryImpl',
        )

    @override_settings(DATA_SOURCE='akshare')
    @patch('saa_collector.services.factory.compound_service_factory.logger')
    def test_initialization_logs_selected_akshare_factory(self, logger_mock):
        factory = CompoundServiceFactory()

        self.assertEqual(factory.impl.__class__.__name__, 'AkshareServiceFactoryImpl')
        logger_mock.info.assert_called_once_with(
            'CompoundServiceFactory initialized: DATA_SOURCE=%s selected_impl=%s',
            'akshare',
            'AkshareServiceFactoryImpl',
        )
