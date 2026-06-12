# -*- coding: utf-8 -*-
from datetime import date, timedelta


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
