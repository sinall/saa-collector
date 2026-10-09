from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from saa_collector.date_expressions import validate_schedule_params
from saa_collector.serializers import InstantCollectJobSerializer
from saa_collector.services import collect_plan_executor as executor
from saa_collector.services.common import index_scope_utils as scope


class HoldingPriceCoverageTest(SimpleTestCase):
    def test_three_month_window_keeps_original_members_without_future_members(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [(date(2025, month, 28),) for month in range(2, 7)],
            [(date(2025, 3, 28), 'EXITED'), (date(2025, 6, 28), 'CURRENT')],
        ]
        resolver = getattr(scope, 'resolve_index_holding_payloads_by_dates', None)
        self.assertIsNotNone(resolver, 'holding-period scope resolver is missing')
        result = resolver(cursor, '000906', [date(2025, 6, 30)], 3)
        self.assertEqual(result[date(2025, 6, 30)][1], {'EXITED', 'CURRENT'})
        self.assertEqual(cursor.execute.call_args_list[0].args[1][-1], date(2025, 6, 30))
        self.assertIn(date(2025, 3, 28), cursor.execute.call_args_list[1].args[1])
        self.assertNotIn(date(2025, 2, 28), cursor.execute.call_args_list[1].args[1])

    def test_invalid_schedule_windows_are_rejected(self):
        for value in (-1, 37, 1.5, True, '3.5'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_schedule_params({'index_lookback_months': value})

    def test_instant_job_rejects_window_for_financial_data(self):
        serializer = InstantCollectJobSerializer(data={
            'data_type': 'balance_sheet', 'stock_scope': 'INDEX',
            'stock_list_code': '000906', 'index_lookback_months': 3,
        })
        self.assertFalse(serializer.is_valid())

    def test_instant_job_preserves_window(self):
        serializer = InstantCollectJobSerializer(data={
            'data_type': 'price_adjust_factor', 'stock_scope': 'INDEX',
            'stock_list_code': '000906', 'index_lookback_months': 3,
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data.get('index_lookback_months'), 3)

    @patch.object(executor, 'resolve_last_trade_days_for_ranges', return_value={date(2025, 6, 30): date(2025, 6, 30)})
    @patch.object(executor, 'connection')
    def test_quote_and_adjustment_collect_same_holding_universe(self, connection, trade_dates):
        connection.cursor.return_value.__enter__.return_value.fetchall.side_effect = [
            [(date(2025, month, 28),) for month in range(3, 7)],
            [(date(2025, 3, 28), 'EXITED'), (date(2025, 6, 28), 'CURRENT')],
        ] * 2
        service = MagicMock()
        for data_type, collect in (
            ('historical_quote', executor.collect_index_historical_quotes),
            ('price_adjust_factor', executor.collect_index_adjust_factors),
        ):
            job = SimpleNamespace(data_type=data_type, config={'params': {'index_lookback_months': 3}})
            collect(job, service, date(2025, 6, 1), date(2025, 6, 30), '000906')
        self.assertEqual(service.collect_historical.call_args.args[0], ['CURRENT', 'EXITED'])
        self.assertEqual(service.collect_adjust_factors.call_args.args[0], ['CURRENT', 'EXITED'])


class HoldingPriceCompletenessTest(SimpleTestCase):
    @patch('saa_collector.services.completeness_service.connection')
    def test_missing_month_end_adjustment_for_exited_member_is_incomplete(self, connection):
        from saa_collector.services.completeness_service import CompletenessService
        service = CompletenessService(index_code='000906', index_lookback_months=3)
        cursor = connection.cursor.return_value.__enter__.return_value
        # Calendar, index dates, index codes, exact-price rows.
        cursor.fetchall.side_effect = [
            [(date(2025, 6, 30),)],
            [(date(2025, 3, 31),), (date(2025, 6, 30),)],
            [(date(2025, 3, 31), 'EXITED'), (date(2025, 6, 30), 'CURRENT')],
            [('CURRENT', date(2025, 6, 30), 1.0), ('EXITED', date(2025, 6, 20), 1.0)],
        ]
        result = service.calculate_all(['price_adjust_factor'], ['2025-06'], 'monthly')
        self.assertEqual(result['matrix']['price_adjust_factor'], [0.5])


class AdjustmentDateQueryTest(SimpleTestCase):
    @patch('django.db.connection')
    def test_range_adjustment_queries_each_trade_day_instead_of_all_market_range(self, connection):
        from saa_collector.services.impl.tushare.quote_service import QuoteServiceImpl
        import pandas as pd
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [(date(2025, 6, 27),), (date(2025, 6, 30),)]
        service = QuoteServiceImpl.__new__(QuoteServiceImpl)
        service._logger = MagicMock()
        service.build_symbols = MagicMock(return_value=['000001'])
        service.save_records = MagicMock()
        service.pro = MagicMock()
        service.pro.query.side_effect = [
            pd.DataFrame([{'ts_code': '000001.SZ', 'trade_date': day, 'adj_factor': 1.0}])
            for day in ('20250627', '20250630')
        ]
        service.collect_adjust_factors(['000001'], start_date=date(2025, 6, 27), end_date=date(2025, 6, 30))
        self.assertEqual([call.kwargs.get('trade_date') for call in service.pro.query.call_args_list], ['20250627', '20250630'])
        self.assertEqual(len(service.save_records.call_args.args[0]), 2)


class HoldingPriceHeatmapViewTest(SimpleTestCase):
    @patch('saa_collector.views.DataCompletenessHeatmapView._resolve_scope')
    @patch('saa_collector.services.completeness_service.CompletenessService')
    @patch('saa_collector.views.cache')
    def test_heatmap_passes_window_and_separates_cache(self, cache, service_class, resolve_scope):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from saa_collector.views import DataCompletenessHeatmapView
        resolve_scope.return_value = {'key': 'index:000906', 'index_code': '000906', 'stock_codes': None, 'label': '中证800'}
        cache.get.return_value = None
        service_class.return_value.generate_periods.return_value = ['2025-06']
        service_class.return_value.calculate_all.return_value = {'matrix': {}}
        request = APIRequestFactory().get('/heatmap/', {'scope': 'index:000906', 'index_lookback_months': '3'})
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
        response = DataCompletenessHeatmapView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(service_class.call_args.kwargs.get('index_lookback_months'), 3)
        self.assertIn('holding:3', cache.get.call_args_list[0].args[0])


class HoldingScheduleValidationTest(SimpleTestCase):
    def test_schedule_rejects_window_for_other_types_or_all_market(self):
        from saa_collector.serializers import CollectScheduleCreateSerializer
        for data_type, stock_scope in [('balance_sheet', 'INDEX'), ('historical_quote', 'ALL')]:
            serializer = CollectScheduleCreateSerializer(data={
                'name': 'window', 'data_type': data_type, 'cron_expression': '0 0 1 * *',
                'params': {'stock_scope': stock_scope, 'stock_list_code': '000906', 'index_lookback_months': 3},
            })
            self.assertFalse(serializer.is_valid())


class HoldingSkipExistingTest(SimpleTestCase):
    @patch.object(executor, 'find_symbols_missing_data', return_value=(['CURRENT', 'EXITED'], 0, 'monthly-period-missing', {}))
    @patch.object(executor, 'record_skip_existing_summary')
    @patch.object(executor, 'connection')
    def test_window_does_not_skip_month_with_only_midmonth_record(self, connection, record, monthly_filter):
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.side_effect = [[(date(2025, 6, 30),)], [('CURRENT', date(2025, 6, 30), 1.0), ('EXITED', date(2025, 6, 20), 1.0)]]
        job = SimpleNamespace(id=1, data_type='price_adjust_factor', config={'params': {'skip_existing': True, 'index_lookback_months': 3}})
        result = executor.filter_existing_symbols_for_job(job, ['CURRENT', 'EXITED'], date(2025, 6, 1), date(2025, 6, 30))
        self.assertEqual(result, ['EXITED'])


class AdjustmentMissingResponseTest(SimpleTestCase):
    def test_nonempty_market_response_without_requested_stock_does_not_crash(self):
        from saa_collector.services.impl.tushare.quote_service import QuoteServiceImpl
        import pandas as pd
        service = QuoteServiceImpl.__new__(QuoteServiceImpl)
        service._logger = MagicMock()
        service.build_symbols = MagicMock(return_value=['000001'])
        service.save_records = MagicMock()
        service.pro = MagicMock()
        service.pro.query.return_value = pd.DataFrame([{'ts_code': '000002.SZ', 'trade_date': '20250630', 'adj_factor': 1.0}])
        service.collect_adjust_factors(['000001'], trade_date=date(2025, 6, 30))
        service.save_records.assert_not_called()


class HoldingWindowBoundaryTest(SimpleTestCase):
    @patch.object(executor, 'resolve_index_constituent_payloads_by_dates')
    def test_zero_window_uses_existing_scope(self, legacy_resolver):
        cursor = MagicMock()
        job = SimpleNamespace(config={'params': {}})
        executor.resolve_price_scope_payloads(job, cursor, '000906', [date(2025, 6, 30)])
        legacy_resolver.assert_called_once_with(cursor, '000906', [date(2025, 6, 30)])

    def test_edit_payload_without_window_does_not_reset_existing_window(self):
        serializer = InstantCollectJobSerializer(data={'data_type': 'historical_quote'})
        self.assertTrue(serializer.is_valid())
        self.assertNotIn('index_lookback_months', serializer.validated_data)

    @patch('django.db.connection')
    def test_nontrading_interval_does_not_call_vendor(self, connection):
        from saa_collector.services.impl.tushare.quote_service import QuoteServiceImpl
        service = QuoteServiceImpl.__new__(QuoteServiceImpl)
        service._logger = MagicMock()
        service.build_symbols = MagicMock(return_value=['000001'])
        service.pro = MagicMock()
        connection.cursor.return_value.__enter__.return_value.fetchall.return_value = []
        service.collect_adjust_factors(['000001'], start_date=date(2025, 6, 28), end_date=date(2025, 6, 29))
        service.pro.query.assert_not_called()


class SelectedMonthlyPriceRangeTest(SimpleTestCase):
    @patch.object(executor, 'resolve_last_trade_days_for_ranges', return_value={date(2025, 4, 30): date(2025, 4, 30), date(2025, 5, 31): date(2025, 5, 30)})
    @patch.object(executor, 'connection')
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_selected_range_collects_two_month_ends_for_each_type(self, factory, connection, trade_dates):
        for data_type, method in [('historical_quote', 'collect_historical'), ('price_adjust_factor', 'collect_adjust_factors')]:
            service = factory.return_value.create_quote_service.return_value
            service.reset_mock()
            job = SimpleNamespace(data_type=data_type, config={
                'symbols': ['000001', '000002'], 'stock_scope': 'SELECTED',
                'params': {'start_date': '2025-04-01', 'end_date': '2025-05-31', 'data_frequency': 'monthly'},
            })
            executor.execute_collect(job)
            calls = getattr(service, method).call_args_list
            self.assertEqual(len(calls), 2)
            self.assertEqual([call.kwargs['trade_date'] for call in calls], [date(2025, 4, 30), date(2025, 5, 30)])
            self.assertEqual([call.args[0] for call in calls], [['000001', '000002']] * 2)
