# -*- coding: utf-8 -*-
import logging
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from saa_collector.services.common import progress as progress_module
from saa_collector.logging_filters import CollectExecutionContextFilter
from saa_collector.services.collect_execution_context import (
    reset_collect_execution_context,
    set_collect_execution_context,
)
from saa_collector.services.common.progress import (
    HistoricalSpanEstimator,
    ProgressLogger,
    count_periods,
    parse_date,
)


class ProgressLoggerTest(unittest.TestCase):
    def test_for_symbols_defaults_to_equal_symbol_progress(self):
        progress = ProgressLogger.for_symbols(
            logging.getLogger(__name__),
            ['000001', '000002'],
        )

        self.assertEqual('symbol', progress.unit)
        self.assertEqual(2, progress.total_items)
        self.assertEqual(2, progress.total_weight)

    def test_historical_span_uses_listing_time_and_start_date(self):
        estimator = HistoricalSpanEstimator(
            listing_times={'000001': '2020-01-01'},
            start_date='2021-01-01',
            end_date='2021-12-31',
            data_type='balance_sheet',
        )

        self.assertEqual(4, estimator.weight('000001'))

    def test_progress_logger_uses_listing_times_context_without_db_lookup(self):
        progress = ProgressLogger.for_symbols(
            logging.getLogger(__name__),
            ['000001', '000002'],
            profile='balance_sheet',
            start_date='2021-01-01',
            end_date='2021-12-31',
            listing_times={
                '000001': '2020-01-01',
                '000002': '2021-10-01',
            },
        )

        self.assertEqual(5, progress.total_weight)

    def test_missing_listing_time_falls_back_to_equal_weight(self):
        estimator = HistoricalSpanEstimator(
            listing_times={},
            start_date='2021-01-01',
            end_date='2021-12-31',
            data_type='balance_sheet',
        )

        self.assertEqual(1, estimator.weight('000001'))

    def test_count_periods_supports_common_frequencies(self):
        start_date = date(2021, 1, 1)
        end_date = date(2021, 12, 31)

        self.assertEqual(12, count_periods(start_date, end_date, 'monthly'))
        self.assertEqual(4, count_periods(start_date, end_date, 'quarterly'))
        self.assertEqual(1, count_periods(start_date, end_date, 'yearly'))

    def test_parse_date_supports_common_formats(self):
        self.assertEqual(date(2021, 1, 2), parse_date('2021-01-02'))
        self.assertEqual(date(2021, 1, 2), parse_date('20210102'))

    def test_load_listing_times_uses_one_batch_query(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            ('000001', '1991-04-03'),
            ('000002', '1991-01-29'),
        ]
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with patch.object(progress_module, 'ConfigService') as config_service_class, \
                patch.object(progress_module.mysql.connector, 'connect', return_value=connection):
            config_service_class.return_value.get_db_config.return_value = {}
            listing_times = progress_module.load_listing_times(['000001', '000002'])

        self.assertEqual('1991-04-03', listing_times['000001'])
        self.assertEqual('1991-01-29', listing_times['000002'])
        self.assertEqual(1, cursor.execute.call_count)
        cursor.execute.assert_called_once_with(
            'SELECT symbol, listing_date FROM saa_stocks WHERE symbol IN (%s,%s)',
            ('000001', '000002'),
        )

    def test_progress_log_includes_unit(self):
        logger = MagicMock()
        progress = ProgressLogger.for_symbols(logger, ['000001'])
        progress.finished('Finished producing statement', '000001')

        log_template = logger.info.call_args.args[0]
        log_args = logger.info.call_args.args[1:]
        rendered = log_template % log_args
        self.assertIn('unit=symbol', rendered)

    def test_progress_log_can_resume_display_count(self):
        logger = MagicMock()
        progress = ProgressLogger.for_symbols(
            logger,
            ['000401', '000402'],
            display_completed_items=77,
            display_total_items=5995,
        )

        progress.finished('Finished producing statement', '000401')

        log_template = logger.info.call_args.args[0]
        log_args = logger.info.call_args.args[1:]
        rendered = log_template % log_args
        self.assertIn('[78/5995 unit=symbol]', rendered)

    def test_logging_filter_includes_collect_execution_context(self):
        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='message',
            args=(),
            exc_info=None,
        )
        token = set_collect_execution_context(
            task_id='celery-task-1',
            plan_id=12,
            job_id=34,
            data_type='financial_statements',
            unit='symbol',
        )
        try:
            CollectExecutionContextFilter().filter(record)
        finally:
            reset_collect_execution_context(token)

        self.assertIn('task_id=celery-task-1', record.collect_context)
        self.assertIn('plan_id=12', record.collect_context)
        self.assertIn('job_id=34', record.collect_context)
        self.assertIn('data_type=financial_statements', record.collect_context)
        self.assertIn('unit=symbol', record.collect_context)


if __name__ == '__main__':
    unittest.main()
