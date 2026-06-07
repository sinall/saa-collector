from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch

from saa_collector.constants import DATA_TYPE_CONFIG
from saa_collector.services.completeness_service import CompletenessService


class CompletenessServiceTest(TestCase):
    def test_core_data_types_declare_completeness_models(self):
        self.assertEqual(DATA_TYPE_CONFIG['trade_days']['completeness_model'], 'calendar')
        self.assertEqual(DATA_TYPE_CONFIG['stock_info']['completeness_model'], 'snapshot_security')
        self.assertEqual(DATA_TYPE_CONFIG['securities']['completeness_model'], 'snapshot_security')
        self.assertEqual(DATA_TYPE_CONFIG['balance_sheet']['completeness_model'], 'periodic_security')
        self.assertEqual(DATA_TYPE_CONFIG['dividend']['completeness_model'], 'event_security')
        self.assertEqual(DATA_TYPE_CONFIG['extras']['completeness_model'], 'trading_day_security')

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

    def test_expected_stock_counts_use_listing_and_delisting_dates(self):
        cursor = Mock()
        cursor.fetchall.return_value = [
            (date(2020, 1, 1), date(2200, 1, 1)),
            (date(2020, 1, 1), date(2020, 12, 31)),
            (date(2021, 1, 1), date(2200, 1, 1)),
        ]

        service = CompletenessService(date_end=date(2021, 12, 31))
        result = service._get_expected_stock_counts(cursor, ['2020', '2021'], 'yearly')

        self.assertEqual(result, {'2020': 2, '2021': 2})
        cursor.execute.assert_called_once_with("SELECT listing_date, delisting_date FROM saa_stocks")

    @patch('saa_collector.services.completeness_service.connection')
    def test_trading_day_security_completeness_uses_trade_day_security_universe(self, connection):
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [
                ('2025-01', 4),
                ('2025-02', 2),
            ],
            [
                ('2025-01', 2),
            ],
        ]
        connection.cursor.return_value.__enter__.return_value = cursor

        service = CompletenessService(date_end=date(2025, 3, 31))
        result = service.calculate_all(['extras'], ['2025-01', '2025-02', '2025-03'], 'monthly')

        self.assertEqual(result['matrix']['extras'], [0.5, 0.0, -1])

    @patch('saa_collector.services.completeness_service.connection')
    def test_trading_day_security_completeness_uses_view_period_keys(self, connection):
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [
                ('2025-Q1', 6),
            ],
            [
                ('2025-Q1', 6),
            ],
        ]
        connection.cursor.return_value.__enter__.return_value = cursor

        service = CompletenessService(date_end=date(2025, 3, 31))
        result = service.calculate_all(['extras'], ['2025-Q1'], 'quarterly')

        self.assertEqual(result['matrix']['extras'], [1.0])
