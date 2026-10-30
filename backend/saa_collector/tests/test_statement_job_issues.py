from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from saa_collector.services.collect_plan_executor import execute_resumable_symbol_loop


class StatementJobIssuesTest(SimpleTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        prefix = 'saa_collector.services.collect_plan_executor.'
        self.mocks = {}
        for name in ('initialize_symbol_progress', 'ensure_plan_not_stopped',
                     'mark_symbol_failure', 'mark_symbol_success', 'record_issue',
                     'release_process_memory', 'ProgressLogger', 'logger'):
            self.mocks[name] = self.stack.enter_context(patch(prefix + name))
        self.mocks['initialize_symbol_progress'].return_value = ['600036', '600000']
        self.job = SimpleNamespace(id=12, plan_id=None, data_type='income')
        self.error = ValueError('source conflict')
        self.error.issue = {'code': 'STATEMENT_FIELD_COVERAGE_LOSS', 'symbol': '600036'}

    def test_single_statement_job_preserves_typed_issue_and_continues(self):
        collect = Mock(side_effect=[self.error, None])
        with self.assertRaisesRegex(RuntimeError, 'income failed for 1 symbols'):
            execute_resumable_symbol_loop(self.job, ['600036', '600000'], collect)
        self.mocks['record_issue'].assert_called_once_with(self.job.id, self.error.issue)
        self.assertEqual(collect.call_count, 2)
        self.mocks['mark_symbol_failure'].assert_called_once_with(self.job.id, '600036')
        self.mocks['mark_symbol_success'].assert_called_once_with(self.job.id, '600000')

    def test_issue_write_failure_propagates_instead_of_losing_evidence(self):
        collect = Mock(side_effect=self.error)
        self.mocks['record_issue'].side_effect = RuntimeError('result persistence failed')
        with self.assertRaisesRegex(RuntimeError, 'result persistence failed'):
            execute_resumable_symbol_loop(self.job, ['600036', '600000'], collect)
        self.assertEqual(collect.call_count, 1)
        self.mocks['release_process_memory'].assert_called_once_with('600036')

    def test_unstructured_error_does_not_invent_financial_evidence(self):
        collect = Mock(side_effect=[ValueError('unrelated failure'), None])
        with self.assertRaises(RuntimeError):
            execute_resumable_symbol_loop(self.job, ['600036', '600000'], collect)
        self.mocks['record_issue'].assert_not_called()
