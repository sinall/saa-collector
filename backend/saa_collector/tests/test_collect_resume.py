from unittest.mock import patch

from django.test import TestCase

from saa_collector.models import CollectJob
from saa_collector.services.collect_plan_executor import execute_collect


class FinancialStatementResumeTest(TestCase):
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
