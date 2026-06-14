from datetime import date
from unittest import TestCase
from unittest.mock import Mock

from saa_collector.services.common.period_utils import (
    generate_monthly_date_ranges,
    resolve_month_end_trade_day,
    resolve_month_end_trade_dates,
)


class PeriodUtilsTest(TestCase):
    def test_resolve_month_end_trade_dates_anchors_each_month_to_latest_trade_day(self):
        trade_day_resolver = Mock(side_effect=lambda value: {
            date(2026, 5, 31): date(2026, 5, 29),
            date(2026, 6, 30): date(2026, 6, 30),
        }[value])

        ranges = generate_monthly_date_ranges(date(2026, 5, 1), date(2026, 6, 30))
        self.assertEqual(
            ranges,
            [
                (date(2026, 5, 1), date(2026, 5, 31)),
                (date(2026, 6, 1), date(2026, 6, 30)),
            ],
        )

        self.assertEqual(
            resolve_month_end_trade_dates(date(2026, 5, 1), date(2026, 6, 30), trade_day_resolver),
            [date(2026, 5, 29), date(2026, 6, 30)],
        )

    def test_resolve_month_end_trade_day_falls_back_to_period_end_when_trade_day_missing(self):
        self.assertEqual(
            resolve_month_end_trade_day(date(2026, 5, 31), trade_day_resolver=lambda _: None),
            date(2026, 5, 31),
        )
