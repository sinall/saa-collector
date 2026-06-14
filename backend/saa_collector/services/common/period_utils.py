# -*- coding: utf-8 -*-
from datetime import date, datetime, timedelta

from saa_collector.date_expressions import get_latest_trade_day_on_or_before


def get_period_label_for_date(value, frequency):
    if frequency == 'daily':
        return value.strftime('%Y-%m-%d')
    if frequency == 'quarterly':
        return f'{value.year}-Q{((value.month - 1) // 3) + 1}'
    if frequency == 'yearly':
        return str(value.year)
    return value.strftime('%Y-%m')


def get_period_range(period, frequency):
    if frequency == 'daily':
        return period, period
    if frequency == 'monthly':
        year, month = int(period[:4]), int(period[5:7])
        if month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        return f'{year}-{month:02d}-01', end.strftime('%Y-%m-%d')
    if frequency == 'quarterly':
        year, quarter = int(period[:4]), int(period[6])
        start_month = (quarter - 1) * 3 + 1
        end_month = quarter * 3
        end_day = 31 if end_month in [3, 12] else 30 if end_month in [4, 6, 9, 11] else 28
        return f'{year}-{start_month:02d}-01', f'{year}-{end_month:02d}-{end_day}'
    if frequency == 'yearly':
        year = int(period)
        return f'{year}-01-01', f'{year}-12-31'
    return period, period


def generate_monthly_date_ranges(start_date, end_date):
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        return []
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    ranges = []
    year = start_date.year
    month = start_date.month
    while True:
        month_start = date(year, month, 1)
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        month_end = next_month - timedelta(days=1)
        period_start = max(start_date, month_start)
        period_end = min(end_date, month_end)
        if period_start <= period_end:
            ranges.append((period_start, period_end))
        if month_end >= end_date:
            break
        month += 1
        if month > 12:
            month = 1
            year += 1
    return ranges


def resolve_month_end_trade_day(period_end, trade_day_resolver=None):
    if isinstance(period_end, datetime):
        period_end = period_end.date()
    if not isinstance(period_end, date):
        return None

    resolver = trade_day_resolver or get_latest_trade_day_on_or_before
    trade_day = resolver(period_end)
    return trade_day or period_end


def resolve_month_end_trade_dates(start_date, end_date, trade_day_resolver=None):
    return [
        resolve_month_end_trade_day(period_end, trade_day_resolver)
        for _, period_end in generate_monthly_date_ranges(start_date, end_date)
    ]
