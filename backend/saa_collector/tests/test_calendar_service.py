from datetime import date
from unittest.mock import MagicMock, patch

from django.test import TestCase

from saa_collector.services.impl.tushare.calendar_service import CalendarServiceImpl


class TushareCalendarServiceLoggingTest(TestCase):
    @patch('saa_collector.services.impl.tushare.calendar_service.mysql.connector.connect')
    def test_save_records_logs_date_range_in_ascending_order(self, connect):
        service = CalendarServiceImpl.__new__(CalendarServiceImpl)
        service._logger = MagicMock()
        service.db_config = {'host': 'localhost'}

        cnx = connect.return_value
        cursor = cnx.cursor.return_value
        records = [
            {'date': date(2026, 5, 25)},
            {'date': date(2026, 5, 12)},
            {'date': date(2026, 5, 21)},
        ]

        service._save_records(records)

        service._logger.info.assert_any_call('Saving 3 trade days to database')
        service._logger.info.assert_any_call('Date range: 2026-05-12 ~ 2026-05-25')
        self.assertEqual(
            [call.args[1][0] for call in cursor.execute.call_args_list],
            [date(2026, 5, 12), date(2026, 5, 21), date(2026, 5, 25)],
        )
        cnx.commit.assert_called_once()
        cursor.close.assert_called_once()
        cnx.close.assert_called_once()
