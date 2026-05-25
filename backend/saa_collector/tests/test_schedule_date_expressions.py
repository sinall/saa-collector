from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from rest_framework.test import APIClient

from saa_collector.date_expressions import (
    normalize_schedule_params,
    parse_schedule_date,
    resolve_schedule_date_range,
)
from saa_collector.models import CollectJob, CollectSchedule
from saa_collector.services.collect_plan_executor import execute_collect


class ScheduleDateExpressionTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._ensure_trade_day_table()

    @classmethod
    def _ensure_trade_day_table(cls):
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE IF NOT EXISTS saa_trade_days (date date PRIMARY KEY)')

    def setUp(self):
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM saa_trade_days')
            for trade_day in ('2026-05-21', '2026-05-22', '2026-05-25', '2026-05-26'):
                cursor.execute('INSERT INTO saa_trade_days (date) VALUES (%s)', [trade_day])

    def test_parse_schedule_date_supports_current_day_aliases(self):
        today = date(2026, 5, 24)

        self.assertEqual(parse_schedule_date('T', today=today), today)
        self.assertEqual(parse_schedule_date('today', today=today), today)

    def test_parse_schedule_date_supports_large_trading_day_offsets(self):
        parsed = parse_schedule_date(
            'T-180',
            today=date(2026, 5, 25),
            trade_day_resolver=lambda base_date, offset: date(2025, 9, 1),
        )

        self.assertEqual(parsed, date(2025, 9, 1))

    def test_parse_schedule_date_supports_calendar_day_offsets(self):
        parsed = parse_schedule_date('T-30d', today=date(2026, 5, 25))

        self.assertEqual(parsed, date(2026, 4, 25))

    def test_parse_schedule_date_supports_trading_day_offsets_without_suffix(self):
        parsed = parse_schedule_date('T-1', today=date(2026, 5, 24))

        self.assertEqual(parsed, date(2026, 5, 22))

    def test_parse_schedule_date_supports_multiple_trading_day_offsets_without_suffix(self):
        parsed = parse_schedule_date('T-2', today=date(2026, 5, 25))

        self.assertEqual(parsed, date(2026, 5, 21))

    def test_parse_schedule_date_rejects_stale_trade_calendar_for_relative_offsets(self):
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM saa_trade_days')
            for trade_day in ('2026-05-08', '2026-05-11'):
                cursor.execute('INSERT INTO saa_trade_days (date) VALUES (%s)', [trade_day])

        with self.assertRaisesRegex(ValueError, 'Trade calendar is stale'):
            parse_schedule_date('T-2', today=date(2026, 5, 25))

    def test_resolve_schedule_date_range_refreshes_trade_calendar_on_stale(self):
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM saa_trade_days')
            for trade_day in ('2026-05-08', '2026-05-11'):
                cursor.execute('INSERT INTO saa_trade_days (date) VALUES (%s)', [trade_day])

        def refresh_trade_calendar(latest_trade_day, base_date):
            with connection.cursor() as cursor:
                current = latest_trade_day + timedelta(days=1)
                while current <= base_date:
                    if current.weekday() < 5:
                        cursor.execute('INSERT OR IGNORE INTO saa_trade_days (date) VALUES (%s)', [current])
                    current += timedelta(days=1)

        start_date, end_date, normalized = resolve_schedule_date_range(
            {
                'date_start': 'T-2',
                'date_end': 'T',
            },
            today=date(2026, 5, 25),
            trade_calendar_refresher=refresh_trade_calendar,
        )

        self.assertEqual(start_date, date(2026, 5, 21))
        self.assertEqual(end_date, date(2026, 5, 25))
        self.assertEqual(normalized['date_start'], 'T-2')
        self.assertEqual(normalized['date_end'], 'T')

    def test_parse_schedule_date_supports_trading_day_offsets_with_td_suffix(self):
        parsed = parse_schedule_date('T-1td', today=date(2026, 5, 24))

        self.assertEqual(parsed, date(2026, 5, 22))

    def test_parse_schedule_date_rejects_invalid_expression(self):
        with self.assertRaises(ValueError):
            parse_schedule_date('T-1x', today=date(2026, 5, 25))

    def test_normalize_schedule_params_keeps_both_schedule_date_aliases(self):
        normalized = normalize_schedule_params({
            'date_start': 'T-180',
            'date_end': 'T-1td',
        })

        self.assertEqual(normalized['date_start'], 'T-180')
        self.assertEqual(normalized['start_date'], 'T-180')
        self.assertEqual(normalized['date_end'], 'T-1td')
        self.assertEqual(normalized['end_date'], 'T-1td')


class CollectScheduleRelativeDateAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.force_authenticate(user=self.user)
        ScheduleDateExpressionTest._ensure_trade_day_table()
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM saa_trade_days')
            for trade_day in ('2026-05-21', '2026-05-22', '2026-05-25', '2026-05-26'):
                cursor.execute('INSERT INTO saa_trade_days (date) VALUES (%s)', [trade_day])

    def test_create_schedule_accepts_and_preserves_relative_date_expressions(self):
        response = self.client.post('/api/collect-schedules/', {
            'name': 'Relative date schedule',
            'data_type': 'historical_quote',
            'symbols': ['000001'],
            'params': {
                'date_start': 'T-2',
                'date_end': 'T-1td',
            },
            'cron_expression': '*/5 * * * *',
            'status': 'ENABLED',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        schedule = CollectSchedule.objects.get()
        self.assertEqual(schedule.params['date_start'], 'T-2')
        self.assertEqual(schedule.params['start_date'], 'T-2')
        self.assertEqual(schedule.params['date_end'], 'T-1td')
        self.assertEqual(schedule.params['end_date'], 'T-1td')

    def test_create_schedule_rejects_invalid_relative_date_expression(self):
        response = self.client.post('/api/collect-schedules/', {
            'name': 'Invalid relative date schedule',
            'data_type': 'historical_quote',
            'symbols': ['000001'],
            'params': {
                'date_start': 'T-1x',
            },
            'cron_expression': '*/5 * * * *',
            'status': 'ENABLED',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data['success'])


class CollectExecutionDateAliasTest(TestCase):
    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    @patch('saa_collector.services.collect_plan_executor.resolve_schedule_date_range')
    def test_execute_collect_treats_date_aliases_identically(
            self, resolve_schedule_date_range_mock, factory_class):
        resolve_schedule_date_range_mock.side_effect = [
            (date(2026, 5, 21), date(2026, 5, 22), {}),
            (date(2026, 5, 21), date(2026, 5, 22), {}),
        ]
        service = factory_class.return_value.create_quote_service.return_value

        alias_job = CollectJob.objects.create(
            data_type='historical_quote',
            config={
                'symbols': ['000001'],
                'params': {
                    'date_start': 'T-2',
                    'date_end': 'T-1td',
                },
            },
        )
        canonical_job = CollectJob.objects.create(
            data_type='historical_quote',
            config={
                'symbols': ['000001'],
                'params': {
                    'start_date': 'T-2',
                    'end_date': 'T-1td',
                },
            },
        )

        execute_collect(alias_job)
        execute_collect(canonical_job)

        expected_calls = [
            (['000001'],),
            (['000001'],),
        ]
        self.assertEqual(
            [call.args for call in service.collect_historical.call_args_list],
            expected_calls,
        )
        self.assertEqual(service.collect_historical.call_args_list[0].kwargs, {
            'start_date': date(2026, 5, 21),
            'end_date': date(2026, 5, 22),
        })
        self.assertEqual(
            service.collect_historical.call_args_list[0].kwargs,
            service.collect_historical.call_args_list[1].kwargs,
        )

    @patch('saa_collector.services.factory.compound_service_factory.CompoundServiceFactory')
    def test_execute_collect_refreshes_stale_trade_calendar_and_proceeds(self, factory_class):
        ScheduleDateExpressionTest._ensure_trade_day_table()
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM saa_trade_days')
            for trade_day in ('2026-05-08', '2026-05-11'):
                cursor.execute('INSERT INTO saa_trade_days (date) VALUES (%s)', [trade_day])

        calendar_service = factory_class.return_value.create_calendar_service.return_value
        service = factory_class.return_value.create_quote_service.return_value
        calendar_service.collect.side_effect = lambda start_date, end_date: _seed_trade_days(start_date, end_date)
        job = CollectJob.objects.create(
            data_type='historical_quote',
            config={
                'symbols': ['000001'],
                'params': {
                    'date_start': 'T-2',
                    'date_end': 'T',
                },
            },
        )

        execute_collect(job)

        calendar_service.collect.assert_called_once_with(
            date(2026, 5, 12),
            date(2026, 5, 25),
        )
        self.assertEqual(
            [call.args for call in service.collect_historical.call_args_list],
            [(['000001'],)],
        )
        self.assertEqual(service.collect_historical.call_args_list[0].kwargs, {
            'start_date': date(2026, 5, 21),
            'end_date': date(2026, 5, 25),
        })


def _seed_trade_days(start_date, end_date):
    with connection.cursor() as cursor:
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                cursor.execute('INSERT OR IGNORE INTO saa_trade_days (date) VALUES (%s)', [current])
            current += timedelta(days=1)
