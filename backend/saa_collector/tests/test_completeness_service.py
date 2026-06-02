from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch

from saa_collector.constants import DATA_TYPE_CONFIG
from saa_collector.services.completeness_service import CompletenessService


class CompletenessServiceTest(TestCase):
    def test_core_data_types_declare_completeness_models(self):
        self.assertEqual(DATA_TYPE_CONFIG['trade_days']['completeness_model'], 'calendar')
        self.assertEqual(DATA_TYPE_CONFIG['stock_info']['completeness_model'], 'snapshot_security')
        self.assertEqual(DATA_TYPE_CONFIG['balance_sheet']['completeness_model'], 'periodic_security')
        self.assertEqual(DATA_TYPE_CONFIG['dividend']['completeness_model'], 'event_security')

    @patch('saa_collector.services.completeness_service.connection')
    def test_event_security_completeness_marks_empty_periods_not_applicable(self, connection):
        cursor = Mock()
        cursor.fetchall.return_value = [
            ('2020', 1),
        ]
        connection.cursor.return_value.__enter__.return_value = cursor

        service = CompletenessService(date_end=date(2021, 12, 31))
        result = service.calculate_all(['dividend'], ['2020', '2021'], 'yearly')

        self.assertEqual(result['matrix']['dividend'], [1.0, -1])
