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
        cursor.fetchall.side_effect = [
            [
                (date(2020, 12, 31),),
                (date(2021, 12, 31),),
            ],
            [
                ('2020', 1),
            ],
        ]
        connection.cursor.return_value.__enter__.return_value = cursor

        service = CompletenessService(date_end=date(2021, 12, 31))
        result = service.calculate_all(['dividend'], ['2020', '2021'], 'yearly')

        self.assertEqual(result['matrix']['dividend'], [1.0, -1])

    def test_expected_stock_counts_use_security_active_ranges(self):
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [
                (date(2020, 12, 31),),
                (date(2021, 12, 31),),
            ],
            [
                ('000001', date(2020, 1, 1), date(2200, 1, 1)),
                ('000002', date(2020, 1, 1), date(2020, 12, 31)),
                ('000003', date(2021, 1, 1), date(2200, 1, 1)),
            ],
        ]

        service = CompletenessService(date_end=date(2021, 12, 31))
        result = service._get_expected_stock_counts(cursor, ['2020', '2021'], 'yearly')

        self.assertEqual(result, {'2020': 2, '2021': 2})
        executed_sql = '\n'.join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertIn('FROM saa_trade_days', executed_sql)
        self.assertIn('FROM saa_securities', executed_sql)
        self.assertNotIn('FROM saa_stocks', executed_sql)

    def test_expected_stock_counts_reuse_trade_days_and_security_ranges(self):
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [
                (date(2020, 12, 31),),
                (date(2021, 12, 31),),
            ],
            [
                ('000001', date(2020, 1, 1), date(2200, 1, 1)),
                ('000002', date(2021, 1, 1), date(2200, 1, 1)),
            ],
        ]

        service = CompletenessService(date_end=date(2021, 12, 31))
        first = service._get_expected_stock_counts(cursor, ['2020', '2021'], 'yearly')
        second = service._get_expected_stock_counts(cursor, ['2020', '2021'], 'yearly')

        self.assertEqual(first, {'2020': 1, '2021': 2})
        self.assertEqual(second, first)
        executed_sql = '\n'.join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertEqual(executed_sql.count('FROM saa_trade_days'), 1)
        self.assertEqual(executed_sql.count('FROM saa_securities'), 1)

    @patch('saa_collector.services.completeness_service.connection')
    def test_trading_day_security_completeness_uses_trade_day_security_universe(self, connection):
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [
                (date(2025, 1, 2),),
                (date(2025, 1, 3),),
                (date(2025, 2, 3),),
            ],
            [
                ('000001', date(2025, 1, 1), date(2025, 1, 31)),
                ('000002', date(2025, 1, 1), date(2200, 1, 1)),
            ],
            [
                ('000001', date(2025, 1, 3)),
                ('000002', date(2025, 1, 3)),
            ],
        ]
        connection.cursor.return_value.__enter__.return_value = cursor

        service = CompletenessService(date_end=date(2025, 3, 31))
        result = service.calculate_all(['extras'], ['2025-01', '2025-02', '2025-03'], 'monthly')

        self.assertEqual(result['matrix']['extras'], [1.0, 0.0, -1])

    @patch('saa_collector.services.completeness_service.connection')
    def test_trading_day_security_completeness_uses_view_period_keys(self, connection):
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [
                (date(2025, 1, 2),),
                (date(2025, 2, 3),),
                (date(2025, 3, 4),),
            ],
            [
                ('000001', date(2025, 1, 1), date(2200, 1, 1)),
            ],
            [
                ('000001', date(2025, 3, 4)),
            ],
        ]
        connection.cursor.return_value.__enter__.return_value = cursor

        service = CompletenessService(date_end=date(2025, 3, 31))
        result = service.calculate_all(['extras'], ['2025-Q1'], 'quarterly')

        self.assertEqual(result['matrix']['extras'], [1.0])

    def test_trading_day_security_expected_counts_use_period_anchor_trade_day(self):
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [
                (date(2025, 1, 2),),
                (date(2025, 1, 3),),
                (date(2025, 2, 3),),
            ],
            [
                ('000001', date(2025, 1, 1), date(2025, 1, 31)),
                ('000002', date(2025, 1, 3), date(2200, 1, 1)),
            ],
        ]

        service = CompletenessService(date_end=date(2025, 2, 28))
        result = service._load_trading_day_security_expected_counts(
            cursor,
            ['2025-01', '2025-02'],
            'monthly',
            '2025-01-01',
            '2025-02-28',
        )

        self.assertEqual(result, {'2025-01': 2, '2025-02': 1})

    @patch('saa_collector.services.completeness_service.connection')
    def test_calculate_all_loads_trade_days_and_securities_once(self, connection):
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [
                (date(2025, 1, 2),),
                (date(2025, 1, 31),),
                (date(2025, 2, 28),),
            ],
            [
                ('000001', date(2025, 1, 1), date(2200, 1, 1)),
                ('000002', date(2025, 1, 1), date(2025, 1, 31)),
            ],
            [
                ('2025-01', 2),
                ('2025-02', 1),
            ],
            [
                ('000001', date(2025, 1, 31)),
                ('000002', date(2025, 1, 31)),
                ('000001', date(2025, 2, 28)),
            ],
        ]
        connection.cursor.return_value.__enter__.return_value = cursor

        service = CompletenessService(date_end=date(2025, 2, 28))
        result = service.calculate_all(['historical_quote', 'extras'], ['2025-01', '2025-02'], 'monthly')

        self.assertEqual(result['matrix']['historical_quote'], [1.0, 1.0])
        self.assertEqual(result['matrix']['extras'], [1.0, 1.0])
        executed_sql = '\n'.join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertEqual(executed_sql.count('FROM saa_trade_days'), 1)
        self.assertEqual(executed_sql.count('FROM saa_securities'), 1)

    @patch('saa_collector.services.completeness_service.connection')
    def test_trading_day_security_index_scope_uses_period_anchor_constituents(self, connection):
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [
                (date(2025, 1, 2),),
                (date(2025, 1, 31),),
                (date(2025, 2, 28),),
            ],
            [
                (date(2025, 1, 15),),
                (date(2025, 2, 15),),
            ],
            [
                (date(2025, 1, 15), '000001'),
                (date(2025, 1, 15), '000002'),
                (date(2025, 2, 15), '000002'),
            ],
            [
                (date(2025, 1, 15),),
                (date(2025, 2, 15),),
            ],
            [
                ('000001', date(2025, 1, 31)),
                ('000002', date(2025, 2, 28)),
            ],
        ]
        connection.cursor.return_value.__enter__.return_value = cursor

        service = CompletenessService(index_code='000906', date_end=date(2025, 2, 28))
        result = service.calculate_all(['extras'], ['2025-01', '2025-02'], 'monthly')

        self.assertEqual(result['matrix']['extras'], [0.5, 1.0])
        executed_sql = '\n'.join(call.args[0] for call in cursor.execute.call_args_list)
        self.assertIn('FROM saa_trade_days', executed_sql)
        self.assertIn('FROM saa_index_weights', executed_sql)
        self.assertIn('FROM saa_extras', executed_sql)
        self.assertIn('date IN', executed_sql)

    @patch('saa_collector.services.completeness_service.connection')
    def test_calculate_all_logs_data_type_duration(self, connection):
        cursor = Mock()
        cursor.fetchall.return_value = [
            ('2025-01', 1),
        ]
        connection.cursor.return_value.__enter__.return_value = cursor

        service = CompletenessService(date_end=date(2025, 1, 31))

        with self.assertLogs('saa_collector.services.completeness_service', level='INFO') as logs:
            service.calculate_all(['trade_days'], ['2025-01'], 'monthly')

        messages = '\n'.join(logs.output)
        self.assertIn('heatmap data_type start key=trade_days', messages)
        self.assertIn('heatmap data_type done key=trade_days', messages)
        self.assertIn('periods=1', messages)
