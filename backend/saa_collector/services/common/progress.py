# -*- coding: utf-8 -*-
import logging
from datetime import date, datetime

import mysql.connector

from saa_collector.constants import DATA_TYPE_CONFIG
from saa_collector.services.common.config_service import ConfigService


WORKLOAD_PROFILES = {
    'default': {
        'estimator': 'equal',
    },
    'stock_info': {
        'estimator': 'equal',
    },
    'financial_statements': {
        'estimator': 'historical_span',
        'data_type': 'financial_statements',
        'factor': 4,
    },
    'balance_sheet': {
        'estimator': 'historical_span',
        'data_type': 'balance_sheet',
    },
    'income': {
        'estimator': 'historical_span',
        'data_type': 'income',
    },
    'cash_flow': {
        'estimator': 'historical_span',
        'data_type': 'cash_flow',
    },
    'dividend': {
        'estimator': 'historical_span',
        'data_type': 'dividend',
    },
    'capital': {
        'estimator': 'historical_span',
        'data_type': 'capital',
    },
    'main_business': {
        'estimator': 'historical_span',
        'data_type': 'main_business',
        'factor': 2,
    },
}


class EqualWorkEstimator(object):
    def weight(self, item):
        return 1


class HistoricalSpanEstimator(object):
    def __init__(self, listing_times, start_date=None, end_date=None,
                 data_type=None, factor=1):
        self.listing_times = listing_times or {}
        self.start_date = parse_date(start_date)
        self.end_date = parse_date(end_date) or date.today()
        self.data_type = data_type
        self.factor = factor or 1
        self.frequency = DATA_TYPE_CONFIG.get(data_type, {}).get('data_frequency')

    def weight(self, symbol):
        listing_time = parse_date(self.listing_times.get(symbol))
        if not listing_time:
            return 1

        effective_start = max(self.start_date or listing_time, listing_time)
        if effective_start > self.end_date:
            return 1

        periods = count_periods(effective_start, self.end_date, self.frequency)
        return max(periods * self.factor, 1)


class ProgressLogger(object):
    def __init__(self, logger, items, unit='item', profile='default', context=None,
                 display_completed_items=0, display_total_items=None):
        self.logger = logger or logging.getLogger()
        self.items = list(items or [])
        self.unit = unit
        self.profile = profile or 'default'
        self.context = context or {}
        self.display_completed_items = int(display_completed_items or 0)
        self.estimator = create_collection_estimator(
            self.profile, self.items, self.context, logger=self.logger
        )
        self.item_weights = {
            item: safe_weight(self.estimator, item)
            for item in self.items
        }
        self.total_items = len(self.items)
        self.display_total_items = int(display_total_items or self.total_items)
        self.total_weight = sum(self.item_weights.values()) or self.total_items or 1
        self.completed_items = 0
        self.completed_weight = 0
        self.started_at = datetime.now()

    @classmethod
    def for_symbols(cls, logger, symbols, profile='default', **context):
        display_completed_items = context.pop('display_completed_items', 0)
        display_total_items = context.pop('display_total_items', None)
        return cls(
            logger=logger,
            items=symbols,
            unit='symbol',
            profile=profile,
            context=context,
            display_completed_items=display_completed_items,
            display_total_items=display_total_items,
        )

    def finished(self, message, item):
        self._advance(item)
        self.logger.info(
            '[%d/%d unit=%s] %s for %s; elapsed=%s, avg=%s/%s, remaining=%s, eta=%s',
            self.display_completed,
            self.display_total_items,
            self.unit,
            message,
            item,
            format_seconds(self.elapsed_seconds),
            format_seconds(self.average_seconds),
            self.unit,
            format_seconds(self.remaining_seconds),
            self.eta.strftime('%Y-%m-%d %H:%M:%S'),
        )

    def failed(self, message, item):
        self._advance(item)
        self.logger.warning(
            '[%d/%d unit=%s] %s for %s; elapsed=%s, avg=%s/%s, remaining=%s, eta=%s',
            self.display_completed,
            self.display_total_items,
            self.unit,
            message,
            item,
            format_seconds(self.elapsed_seconds),
            format_seconds(self.average_seconds),
            self.unit,
            format_seconds(self.remaining_seconds),
            self.eta.strftime('%Y-%m-%d %H:%M:%S'),
        )

    def _advance(self, item):
        self.completed_items += 1
        self.completed_weight += self.item_weights.get(item, 1)

    @property
    def display_completed(self):
        return self.display_completed_items + self.completed_items

    @property
    def elapsed_seconds(self):
        return max((datetime.now() - self.started_at).total_seconds(), 0)

    @property
    def average_seconds(self):
        if self.completed_items <= 0:
            return 0
        return self.elapsed_seconds / self.completed_items

    @property
    def remaining_seconds(self):
        if self.completed_weight <= 0:
            return 0
        remaining_weight = max(self.total_weight - self.completed_weight, 0)
        return (self.elapsed_seconds / self.completed_weight) * remaining_weight

    @property
    def eta(self):
        return datetime.fromtimestamp(datetime.now().timestamp() + self.remaining_seconds)


def create_collection_estimator(profile, items, context=None, logger=None):
    profile_config = WORKLOAD_PROFILES.get(profile) or WORKLOAD_PROFILES['default']
    if profile_config['estimator'] == 'equal':
        return EqualWorkEstimator()

    try:
        listing_times = (context or {}).get('listing_times')
        if listing_times is None:
            listing_times = load_listing_times(items)
        return HistoricalSpanEstimator(
            listing_times=listing_times,
            start_date=(context or {}).get('start_date'),
            end_date=(context or {}).get('end_date'),
            data_type=profile_config.get('data_type'),
            factor=profile_config.get('factor', 1),
        )
    except Exception as e:
        (logger or logging.getLogger()).warning(
            'Failed to create progress estimator for profile %s, using equal weights: %s',
            profile, e
        )
        return EqualWorkEstimator()


def load_listing_times(symbols):
    symbols = list(symbols or [])
    if not symbols:
        return {}

    config_service = ConfigService()
    cnx = mysql.connector.connect(**config_service.get_db_config())
    cursor = None
    try:
        placeholders = ','.join(['%s'] * len(symbols))
        query = (
            'SELECT symbol, listing_time FROM saa_stocks '
            'WHERE symbol IN ({})'
        ).format(placeholders)
        cursor = cnx.cursor()
        cursor.execute(query, tuple(symbols))
        return {
            symbol: listing_time
            for symbol, listing_time in cursor.fetchall()
        }
    finally:
        if cursor:
            cursor.close()
        cnx.close()


def safe_weight(estimator, item):
    try:
        weight = estimator.weight(item)
        if weight <= 0:
            return 1
        return weight
    except Exception:
        return 1


def count_periods(start_date, end_date, frequency):
    if not frequency:
        return 1
    if frequency == 'yearly':
        return end_date.year - start_date.year + 1
    if frequency == 'quarterly':
        return quarter_index(end_date) - quarter_index(start_date) + 1
    if frequency == 'monthly':
        return month_index(end_date) - month_index(start_date) + 1
    if frequency == 'daily':
        return (end_date - start_date).days + 1
    return 1


def quarter_index(value):
    return value.year * 4 + ((value.month - 1) // 3)


def month_index(value):
    return value.year * 12 + value.month


def parse_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        for date_format in ('%Y-%m-%d', '%Y%m%d'):
            try:
                return datetime.strptime(value, date_format).date()
            except ValueError:
                pass
    return None


def format_seconds(seconds):
    seconds = int(max(seconds, 0))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return '{:02d}:{:02d}:{:02d}'.format(hours, minutes, secs)
