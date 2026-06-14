from datetime import date
from unittest.mock import patch

from django.test import TestCase

from saa_collector.models import CollectJob
from saa_collector.services.collect_plan_executor import execute_collect


class FinancialStatementResumeTest(TestCase):
    def test_collect_job_complete_preserves_config_updates_from_executor(self):
        job = CollectJob.objects.create(
            data_type='historical_quote',
            config={'params': {'skip_existing': True}},
        )
        updated_job = CollectJob.objects.get(id=job.id)
        updated_job.config = {
            **updated_job.config,
            'skip_existing_summary': {
                'kept_symbols': 0,
                'period_window': '2025-04',
            },
        }
        updated_job.save(update_fields=['config'])

        job.complete(success=True, message='执行完成')

        job.refresh_from_db()
        self.assertEqual(job.config['skip_existing_summary'], {
            'kept_symbols': 0,
            'period_window': '2025-04',
        })

    @patch('saa_collector.services.collect_plan_executor.release_process_memory')
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_financial_statements_filters_explicit_symbols_to_a_stocks(
            self, factory_class, release_process_memory):
        job = CollectJob.objects.create(
            data_type='financial_statements',
            config={
                'symbols': ['000001', '510300', '000002'],
                'params': {},
            },
        )
        service = factory_class.return_value.create_statement_service.return_value
        service.filter_a_stock_symbols.return_value = ['000001', '000002']

        def produce(symbols, start_date=None, on_symbol_success=None,
                    on_symbol_failure=None, after_symbol=None, **kwargs):
            self.assertEqual(symbols, ['000001', '000002'])
            on_symbol_success('000001')
            after_symbol('000001')
            on_symbol_success('000002')
            after_symbol('000002')

        service.produce.side_effect = produce

        execute_collect(job)

        service.filter_a_stock_symbols.assert_called_once_with(['000001', '000002', '510300'])
        job.refresh_from_db()
        self.assertNotIn('remaining_symbols', job.config)
        self.assertEqual(release_process_memory.call_count, 2)

    @patch('saa_collector.services.collect_plan_executor.release_process_memory')
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_financial_statements_resume_initializes_remaining_symbols_on_first_run(
            self, factory_class, release_process_memory):
        job = CollectJob.objects.create(
            data_type='financial_statements',
            config={
                'symbols': ['000001', '000002'],
                'params': {},
            },
        )
        service = factory_class.return_value.create_statement_service.return_value
        service.filter_a_stock_symbols.side_effect = lambda symbols: sorted(symbols)

        def produce(symbols, start_date=None, on_symbol_success=None,
                    on_symbol_failure=None, after_symbol=None, **kwargs):
            self.assertEqual(symbols, ['000001', '000002'])
            on_symbol_success('000001')
            after_symbol('000001')
            on_symbol_failure('000002')
            after_symbol('000002')

        service.produce.side_effect = produce

        with self.assertRaisesRegex(RuntimeError, 'failed for 1 symbols'):
            execute_collect(job)

        job.refresh_from_db()
        self.assertEqual(job.config['remaining_symbols'], ['000002'])
        self.assertEqual(job.config['failed_symbols'], ['000002'])
        self.assertEqual(release_process_memory.call_count, 2)

    @patch('saa_collector.services.collect_plan_executor.release_process_memory')
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_financial_statements_resume_uses_remaining_symbols_and_clears_finished_progress(
            self, factory_class, release_process_memory):
        job = CollectJob.objects.create(
            data_type='financial_statements',
            config={
                'symbols': ['000001', '000002', '000003'],
                'remaining_symbols': ['000002', '000003'],
                'failed_symbols': ['000002'],
                'params': {},
            },
        )
        service = factory_class.return_value.create_statement_service.return_value
        service.filter_a_stock_symbols.side_effect = lambda symbols: sorted(symbols)

        def produce(symbols, start_date=None, on_symbol_success=None,
                    on_symbol_failure=None, after_symbol=None, **kwargs):
            self.assertEqual(symbols, ['000002', '000003'])
            on_symbol_success('000002')
            after_symbol('000002')
            on_symbol_failure('000003')
            after_symbol('000003')

        service.produce.side_effect = produce

        with self.assertRaisesRegex(RuntimeError, 'failed for 1 symbols'):
            execute_collect(job)

        job.refresh_from_db()
        self.assertEqual(job.config['remaining_symbols'], ['000003'])
        self.assertEqual(job.config['failed_symbols'], ['000003'])
        self.assertEqual(release_process_memory.call_count, 2)
        _, args, kwargs = service.produce.mock_calls[0]
        self.assertEqual(kwargs['progress_total_symbols'], 3)
        self.assertEqual(kwargs['progress_completed_symbols'], 1)


class FloatingEndDateCollectTest(TestCase):
    @patch('saa_collector.services.collect_plan_executor.filter_existing_symbols_for_job', side_effect=lambda job, symbols, start_date, end_date: symbols)
    @patch('saa_collector.services.collect_plan_executor.timezone.localdate')
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_historical_quote_end_date_mode_execution_day_resolves_to_today(
            self, factory_class, localdate, filter_existing_symbols_for_job):
        localdate.return_value = date(2026, 6, 13)
        job = CollectJob.objects.create(
            data_type='historical_quote',
            config={
                'symbols': ['000001'],
                'params': {
                    'start_date': '2024-01-01',
                    'end_date_mode': 'EXECUTION_DAY',
                },
            },
        )
        service = factory_class.return_value.create_quote_service.return_value
        service.build_symbols.side_effect = lambda symbols: symbols

        execute_collect(job)

        service.collect_historical.assert_called_once_with(
            ['000001'],
            start_date=date(2024, 1, 1),
            end_date=date(2026, 6, 13),
        )
        filter_existing_symbols_for_job.assert_called_once()

    @patch('saa_collector.services.collect_plan_executor.release_process_memory')
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_financial_statements_resume_clears_progress_when_all_remaining_symbols_succeed(
            self, factory_class, release_process_memory):
        job = CollectJob.objects.create(
            data_type='financial_statements',
            config={
                'symbols': ['000001', '000002'],
                'remaining_symbols': ['000002'],
                'failed_symbols': ['000002'],
                'params': {},
            },
        )
        service = factory_class.return_value.create_statement_service.return_value
        service.filter_a_stock_symbols.side_effect = lambda symbols: sorted(symbols)

        def produce(symbols, start_date=None, on_symbol_success=None,
                    on_symbol_failure=None, after_symbol=None, **kwargs):
            self.assertEqual(symbols, ['000002'])
            on_symbol_success('000002')
            after_symbol('000002')

        service.produce.side_effect = produce

        execute_collect(job)

        job.refresh_from_db()
        self.assertNotIn('remaining_symbols', job.config)
        self.assertNotIn('failed_symbols', job.config)
        release_process_memory.assert_called_once_with('000002')

    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_financial_statements_resume_does_not_call_service_when_all_symbols_completed(
            self, factory_class):
        job = CollectJob.objects.create(
            data_type='financial_statements',
            config={
                'symbols': ['000001', '000002'],
                'remaining_symbols': [],
                'params': {},
            },
        )
        service = factory_class.return_value.create_statement_service.return_value
        service.filter_a_stock_symbols.side_effect = lambda symbols: sorted(symbols)

        execute_collect(job)

        job.refresh_from_db()
        self.assertNotIn('remaining_symbols', job.config)
        service.produce.assert_not_called()


class SymbolLoopResumeTest(TestCase):
    @patch('saa_collector.services.collect_plan_executor.release_process_memory')
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_capital_resume_tracks_symbol_success_and_failure(
            self, factory_class, release_process_memory):
        job = CollectJob.objects.create(
            data_type='capital',
            config={
                'symbols': ['000001', '000002'],
                'params': {},
            },
        )
        service = factory_class.return_value.create_capital_service.return_value
        service.filter_a_stock_symbols.side_effect = lambda symbols: sorted(symbols)

        def collect(symbols, start_date=None, progress_enabled=True):
            self.assertFalse(progress_enabled)
            if symbols == ['000002']:
                raise RuntimeError('boom')

        service.collect.side_effect = collect

        with self.assertRaisesRegex(RuntimeError, 'capital failed for 1 symbols'):
            execute_collect(job)

        service.collect.assert_any_call(['000001'], None, progress_enabled=False)
        service.collect.assert_any_call(['000002'], None, progress_enabled=False)
        job.refresh_from_db()
        self.assertEqual(job.config['remaining_symbols'], ['000002'])
        self.assertEqual(job.config['failed_symbols'], ['000002'])
        self.assertEqual(release_process_memory.call_count, 2)

    @patch('saa_collector.services.collect_plan_executor.release_process_memory')
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_capital_resume_uses_remaining_symbols(
            self, factory_class, release_process_memory):
        job = CollectJob.objects.create(
            data_type='capital',
            config={
                'symbols': ['000001', '000002', '000003'],
                'remaining_symbols': ['000002', '000003'],
                'failed_symbols': ['000002'],
                'params': {},
            },
        )
        service = factory_class.return_value.create_capital_service.return_value
        service.filter_a_stock_symbols.side_effect = lambda symbols: sorted(symbols)

        execute_collect(job)

        service.collect.assert_any_call(['000002'], None, progress_enabled=False)
        service.collect.assert_any_call(['000003'], None, progress_enabled=False)
        self.assertEqual(service.collect.call_count, 2)
        job.refresh_from_db()
        self.assertNotIn('remaining_symbols', job.config)
        self.assertNotIn('failed_symbols', job.config)
        self.assertEqual(release_process_memory.call_count, 2)

    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_capital_resume_skips_service_when_all_symbols_completed(
            self, factory_class):
        job = CollectJob.objects.create(
            data_type='capital',
            config={
                'symbols': ['000001', '000002'],
                'remaining_symbols': [],
                'params': {},
            },
        )
        service = factory_class.return_value.create_capital_service.return_value
        service.filter_a_stock_symbols.side_effect = lambda symbols: sorted(symbols)

        execute_collect(job)

        service.collect.assert_not_called()
        job.refresh_from_db()
        self.assertNotIn('remaining_symbols', job.config)


class SkipExistingCollectTest(TestCase):
    @patch('saa_collector.services.collect_plan_executor.resolve_index_constituent_payloads_by_dates')
    @patch('saa_collector.services.collect_plan_executor.filter_existing_symbols_for_job', side_effect=lambda job, symbols, start_date, end_date: symbols)
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_historical_quote_index_scope_collects_monthly_constituents(
            self, factory_class, filter_existing_symbols_for_job, resolve_payloads):
        job = CollectJob.objects.create(
            data_type='historical_quote',
            config={
                'symbols': [],
                'stock_scope': 'INDEX',
                'stock_list_code': '000906',
                'params': {
                    'start_date': '2025-04-01',
                    'end_date': '2025-05-31',
                },
            },
        )
        service = factory_class.return_value.create_quote_service.return_value
        service.build_symbols.side_effect = lambda symbols: sorted(symbols)
        resolve_payloads.return_value = {
            date(2025, 4, 30): (date(2025, 4, 30), {'000001', '000002'}),
            date(2025, 5, 31): (date(2025, 5, 31), {'000002', '000003'}),
        }

        execute_collect(job)

        self.assertEqual(
            [call.args[0] for call in service.collect_historical.call_args_list],
            [['000001', '000002'], ['000002', '000003']],
        )
        self.assertEqual(service.collect_historical.call_args_list[0].kwargs, {
            'trade_date': date(2025, 4, 30),
            'start_date': date(2025, 4, 1),
            'end_date': date(2025, 4, 30),
        })
        self.assertEqual(service.collect_historical.call_args_list[1].kwargs, {
            'trade_date': date(2025, 5, 31),
            'start_date': date(2025, 5, 1),
            'end_date': date(2025, 5, 31),
        })
        self.assertEqual(filter_existing_symbols_for_job.call_count, 2)

    @patch('saa_collector.services.collect_plan_executor.find_symbols_missing_data')
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_historical_quote_skip_existing_collects_only_symbols_with_missing_periods(
            self, factory_class, find_symbols_missing_data):
        job = CollectJob.objects.create(
            data_type='historical_quote',
            config={
                'symbols': ['000001', '000002', '000003'],
                'params': {
                    'start_date': '2024-01-01',
                    'end_date': '2024-12-31',
                    'skip_existing': True,
                },
            },
        )
        service = factory_class.return_value.create_quote_service.return_value
        service.build_symbols.side_effect = lambda symbols: sorted(symbols)
        find_symbols_missing_data.return_value = (['000002'], 2, 'monthly-period-missing')

        execute_collect(job)

        service.collect_historical.assert_called_once()
        args, kwargs = service.collect_historical.call_args
        self.assertEqual(args[0], ['000002'])
        self.assertEqual(str(kwargs['start_date']), '2024-01-01')
        self.assertEqual(str(kwargs['end_date']), '2024-12-31')
        job.refresh_from_db()
        self.assertEqual(job.config['skip_existing_summary']['requested_symbols'], 3)
        self.assertEqual(job.config['skip_existing_summary']['kept_symbols'], 1)
        self.assertEqual(job.config['skip_existing_summary']['skipped_symbols'], 2)

    @patch('saa_collector.services.collect_plan_executor.query_existing_symbol_periods')
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_historical_quote_skip_existing_summary_includes_period_details(
            self, factory_class, query_existing_symbol_periods):
        job = CollectJob.objects.create(
            data_type='historical_quote',
            config={
                'symbols': ['000001', '000002'],
                'params': {
                    'start_date': '2025-04-01',
                    'end_date': '2025-05-31',
                    'skip_existing': True,
                },
            },
        )
        service = factory_class.return_value.create_quote_service.return_value
        service.build_symbols.side_effect = lambda symbols: sorted(symbols)
        query_existing_symbol_periods.return_value = {
            '000001': {'2025-04', '2025-05'},
            '000002': {'2025-04'},
        }

        execute_collect(job)

        service.collect_historical.assert_called_once()
        self.assertEqual(service.collect_historical.call_args.args[0], ['000002'])
        job.refresh_from_db()
        summary = job.config['skip_existing_summary']
        self.assertEqual(summary['period_window'], '2025-04..2025-05')
        self.assertEqual(summary['expected_period_count'], 2)
        self.assertEqual(summary['kept_sample'], ['000002'])
        self.assertEqual(summary['skipped_sample'], ['000001'])
        self.assertEqual(summary['missing_periods_sample'], {'000002': ['2025-05']})

    @patch('saa_collector.services.collect_plan_executor.find_symbols_missing_data')
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_historical_quote_skip_existing_skips_external_call_when_all_symbols_exist(
            self, factory_class, find_symbols_missing_data):
        job = CollectJob.objects.create(
            data_type='historical_quote',
            config={
                'symbols': ['000001', '000002'],
                'params': {
                    'start_date': '2024-01-01',
                    'end_date': '2024-12-31',
                    'skip_existing': True,
                },
            },
        )
        service = factory_class.return_value.create_quote_service.return_value
        service.build_symbols.side_effect = lambda symbols: sorted(symbols)
        find_symbols_missing_data.return_value = ([], 2, 'monthly-period-missing')

        execute_collect(job)

        service.collect_historical.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.config['skip_existing_summary']['kept_symbols'], 0)

    @patch('saa_collector.services.collect_plan_executor.resolve_stock_status_target_dates')
    @patch('saa_collector.services.collect_plan_executor.stock_status_target_date_is_complete')
    @patch('saa_collector.services.common.stock_status_service.StockStatusService')
    def test_extras_skip_existing_skips_external_call_when_all_target_dates_complete(
            self, service_class, target_date_is_complete, resolve_target_dates):
        resolve_target_dates.return_value = [date(2024, 5, 31), date(2024, 6, 28)]
        target_date_is_complete.side_effect = [True, True]
        job = CollectJob.objects.create(
            data_type='extras',
            config={
                'symbols': ['000001'],
                'params': {
                    'start_date': '2024-05-01',
                    'end_date': '2024-06-30',
                    'data_frequency': 'monthly',
                    'skip_existing': True,
                },
                'stock_scope': 'SELECTED',
            },
        )

        execute_collect(job)

        service_class.assert_not_called()
        self.assertEqual(target_date_is_complete.call_count, 2)

    @patch('saa_collector.services.collect_plan_executor.resolve_stock_status_target_dates')
    @patch('saa_collector.services.collect_plan_executor.stock_status_target_date_is_complete')
    @patch('saa_collector.services.collect_plan_executor.resolve_index_constituent_payloads_by_dates')
    @patch('saa_collector.services.common.stock_status_service.StockStatusService')
    def test_extras_skip_existing_collects_only_missing_target_dates(
            self, service_class, resolve_index_payloads, target_date_is_complete, resolve_target_dates):
        resolve_target_dates.return_value = [date(2024, 5, 31), date(2024, 6, 28)]
        target_date_is_complete.side_effect = [True, False]
        resolve_index_payloads.return_value = {}
        job = CollectJob.objects.create(
            data_type='extras',
            config={
                'symbols': ['000001'],
                'params': {
                    'start_date': '2024-05-01',
                    'end_date': '2024-06-30',
                    'data_frequency': 'monthly',
                    'skip_existing': True,
                },
                'stock_scope': 'SELECTED',
            },
        )

        execute_collect(job)

        service_class.return_value.collect.assert_called_once_with(
            target_dates=[date(2024, 6, 28)],
            symbols=['000001'],
        )
