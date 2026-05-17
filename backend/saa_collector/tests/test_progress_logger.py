# -*- coding: utf-8 -*-
import logging
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from saa_collector.services.common import progress as progress_module
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
            'SELECT symbol, listing_time FROM saa_stocks WHERE symbol IN (%s,%s)',
            ('000001', '000002'),
        )


if __name__ == '__main__':
    unittest.main()
