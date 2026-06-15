from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
from django.test import SimpleTestCase

from saa_collector.services.common.sw_industry_service import SwIndustryService


class SwIndustryServiceTest(SimpleTestCase):
    @patch('saa_collector.services.common.sw_industry_service.ConfigService')
    @patch('saa_collector.services.common.sw_industry_service.get_tushare_client')
    @patch('saa_collector.services.common.sw_industry_service.mysql.connector.connect')
    @patch('saa_collector.services.common.sw_industry_service.DB')
    def test_collect_industries_saves_sw_l1_dictionary(self, db_class, connect, get_client, config_service_class):
        config_service_class.return_value.get_config.return_value = {
            'saa_collector': {'tushare_api': {'token': 'token', 'rate_limit': 10}}
        }
        config_service_class.return_value.get_db_config.return_value = {'host': 'db'}
        pro = Mock()
        pro.query.return_value = pd.DataFrame([
            {'index_code': '801010.SI', 'industry_name': '农林牧渔', 'level': 'L1'},
            {'index_code': '801020.SI', 'industry_name': '煤炭', 'level': 'L1'},
        ])
        get_client.return_value = pro
        cursor = Mock()
        cursor.fetchall.return_value = [('801010', date(2004, 2, 9))]
        connection = Mock()
        connection.cursor.return_value = cursor
        connect.return_value = connection

        service = SwIndustryService()
        service.collect_industries(date(2026, 5, 29))

        self.assertEqual(pro.query.call_args.args[0], 'index_classify')
        self.assertEqual(pro.query.call_args.kwargs['level'], 'L1')
        self.assertEqual(pro.query.call_args.kwargs['src'], 'SW2021')
        db_class.return_value.to_sql.assert_called_once_with(
            [
                {'category': 'sw_l1', 'index': '801010', 'name': '农林牧渔', 'start_date': date(2004, 2, 9)},
                {'category': 'sw_l1', 'index': '801020', 'name': '煤炭', 'start_date': date(2026, 5, 29)},
            ],
            connection,
            'saa_industries',
            ['category', 'index'],
        )
        cursor.close.assert_called_once()
        connection.close.assert_called_once()

    @patch('saa_collector.services.common.sw_industry_service.ConfigService')
    @patch('saa_collector.services.common.sw_industry_service.get_tushare_client')
    @patch('saa_collector.services.common.sw_industry_service.mysql.connector.connect')
    @patch('saa_collector.services.common.sw_industry_service.DB')
    def test_collect_industry_stocks_saves_sw_l1_constituents(self, db_class, connect, get_client, config_service_class):
        config_service_class.return_value.get_config.return_value = {
            'saa_collector': {'tushare_api': {'token': 'token', 'rate_limit': 10}}
        }
        config_service_class.return_value.get_db_config.return_value = {'host': 'db'}
        cursor = Mock()
        cursor.fetchall.return_value = [('801010',), ('801020',)]
        connection = Mock()
        connection.cursor.return_value = cursor
        connect.return_value = connection
        pro = Mock()
        pro.query.side_effect = [
            pd.DataFrame([{'l1_code': '801010.SI', 'ts_code': '000001.SZ', 'name': '平安银行'}]),
            pd.DataFrame([{'l1_code': '801020.SI', 'ts_code': '600000.SH', 'name': '浦发银行'}]),
        ]
        get_client.return_value = pro

        service = SwIndustryService()
        service.collect_industry_stocks(None, date(2026, 5, 29))

        self.assertEqual(pro.query.call_args_list[0].args[0], 'index_member_all')
        self.assertEqual(pro.query.call_args_list[0].kwargs['l1_code'], '801010.SI')
        self.assertEqual(pro.query.call_args_list[0].kwargs['is_new'], 'Y')
        self.assertEqual(pro.query.call_args_list[1].kwargs['l1_code'], '801020.SI')
        db_class.return_value.to_sql.assert_called_once_with(
            [
                {'industry_code': '801010', 'date': date(2026, 5, 29), 'code': '000001'},
                {'industry_code': '801020', 'date': date(2026, 5, 29), 'code': '600000'},
            ],
            connection,
            'saa_industry_stocks',
            ['industry_code', 'date', 'code'],
        )
        cursor.close.assert_called_once()
        connection.close.assert_called_once()

    @patch('saa_collector.services.common.sw_industry_service.ConfigService')
    @patch('saa_collector.services.common.sw_industry_service.get_tushare_client')
    @patch('saa_collector.services.common.sw_industry_service.mysql.connector.connect')
    @patch('saa_collector.services.common.sw_industry_service.DB')
    def test_collect_industry_stocks_supports_monthly_backfill_dates(
            self, db_class, connect, get_client, config_service_class):
        config_service_class.return_value.get_config.return_value = {
            'saa_collector': {'tushare_api': {'token': 'token', 'rate_limit': 10}}
        }
        config_service_class.return_value.get_db_config.return_value = {'host': 'db'}
        cursor = Mock()
        cursor.fetchall.return_value = [('801010',)]
        connection = Mock()
        connection.cursor.return_value = cursor
        connect.return_value = connection
        pro = Mock()
        pro.query.return_value = pd.DataFrame([
            {'l1_code': '801010.SI', 'ts_code': '000001.SZ', 'name': '平安银行'},
        ])
        get_client.return_value = pro

        service = SwIndustryService()
        service.collect_industry_stocks(None, target_dates=[date(2025, 5, 30), date(2025, 6, 30)])

        self.assertEqual(pro.query.call_count, 2)
        self.assertEqual(pro.query.call_args_list[0].args[0], 'index_member_all')
        self.assertEqual(pro.query.call_args_list[0].kwargs['l1_code'], '801010.SI')
        self.assertEqual(pro.query.call_args_list[1].kwargs['l1_code'], '801010.SI')
        db_class.return_value.to_sql.assert_called_once_with(
            [
                {'industry_code': '801010', 'date': date(2025, 5, 30), 'code': '000001'},
                {'industry_code': '801010', 'date': date(2025, 6, 30), 'code': '000001'},
            ],
            connection,
            'saa_industry_stocks',
            ['industry_code', 'date', 'code'],
        )
        connection.close.assert_called_once()

    @patch('saa_collector.services.common.sw_industry_service.ConfigService')
    @patch('saa_collector.services.common.sw_industry_service.get_tushare_client')
    @patch('saa_collector.services.common.sw_industry_service.mysql.connector.connect')
    @patch('saa_collector.services.common.sw_industry_service.DB')
    def test_collect_industry_stocks_skips_provider_shape_errors(self, db_class, connect, get_client, config_service_class):
        config_service_class.return_value.get_config.return_value = {
            'saa_collector': {'tushare_api': {'token': 'token', 'rate_limit': 10}}
        }
        config_service_class.return_value.get_db_config.return_value = {'host': 'db'}
        cursor = Mock()
        cursor.fetchall.return_value = [('801010',), ('801020',)]
        connection = Mock()
        connection.cursor.return_value = cursor
        connect.return_value = connection
        pro = Mock()
        pro.query.side_effect = [
            KeyError("['证券代码', '证券名称', '最新权重', '计入日期'] not in index"),
            pd.DataFrame([{'l1_code': '801020.SI', 'ts_code': '600000.SH', 'name': '浦发银行'}]),
        ]
        get_client.return_value = pro

        service = SwIndustryService()
        with self.assertLogs(level='WARNING') as logs:
            service.collect_industry_stocks(None, date(2026, 5, 29))

        self.assertIn('Skipping SW industry constituents: industry_code=801010', logs.output[0])
        db_class.return_value.to_sql.assert_called_once_with(
            [
                {'industry_code': '801020', 'date': date(2026, 5, 29), 'code': '600000'},
            ],
            connection,
            'saa_industry_stocks',
            ['industry_code', 'date', 'code'],
        )
        connection.close.assert_called_once()
