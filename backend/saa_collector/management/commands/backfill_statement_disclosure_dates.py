# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from saa_collector.services.collect_execution_context import (
    reset_collect_execution_context,
    set_collect_execution_context,
)
from saa_collector.services.impl.tushare.statement_service import StatementServiceImpl


STATEMENT_RESOURCES = (
    ('balancesheet', 'saa_raw_balance_sheet'),
    ('income', 'saa_raw_income_statement'),
    ('cashflow', 'saa_raw_cash_flow_statement'),
)


class Command(BaseCommand):
    help = 'Backfill raw financial statement disclosure_date from Tushare ann_date/f_ann_date.'

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument('--symbols', nargs='+', help='Stock symbols to backfill, e.g. 000001 600519.')
        scope.add_argument('--index', dest='index_code', help='Index code whose historical constituent union should be backfilled.')
        scope.add_argument('--all', action='store_true', help='Backfill all A-share stocks.')
        parser.add_argument('--start-date', help='Statement query start date, YYYY-MM-DD.')
        parser.add_argument('--dry-run', action='store_true', help='Only resolve scope and estimate requests; do not call Tushare or update DB.')
        parser.add_argument('--limit', type=int, help='Limit resolved symbols for sampling.')
        parser.add_argument('--rate-limit', type=int, help='Optional requests-per-minute override for this process.')
        parser.add_argument(
            '--api-cache-policy',
            choices=['prefer-valid', 'bypass', 'disabled'],
            default='prefer-valid',
            help='Use valid API cache by default; bypass or disable when requested.',
        )

    def handle(self, *args, **options):
        with quiet_database_debug_logging():
            start_date = parse_date(options.get('start_date'))
            symbols = resolve_symbols(
                symbols=options.get('symbols'),
                index_code=options.get('index_code'),
                all_stocks=options.get('all'),
                limit=options.get('limit'),
            )
            estimated_requests = len(symbols) * len(STATEMENT_RESOURCES)
            self.stdout.write(
                'scope_resolved symbols={} estimated_tushare_requests={}'.format(
                    len(symbols),
                    estimated_requests,
                )
            )
            if options.get('rate_limit'):
                minutes = estimated_requests / float(options['rate_limit']) if options['rate_limit'] else 0
                self.stdout.write('estimated_rate_limit_minutes={:.1f}'.format(minutes))
            if options.get('dry_run'):
                return

            context_token = set_collect_execution_context(
                api_cache_enabled=options['api_cache_policy'] != 'disabled',
                api_cache_bypass=options['api_cache_policy'] == 'bypass',
            )
            try:
                service = StatementServiceImpl()
                apply_rate_limit_override(service, options.get('rate_limit'))
                updated_rows = 0
                failures = []
                for symbol in symbols:
                    for sub_resource, table in STATEMENT_RESOURCES:
                        try:
                            records = query_statement_disclosure_records(service, sub_resource, table, symbol, start_date)
                            updated = update_disclosure_dates(table, records)
                            updated_rows += updated
                        except Exception as exc:
                            failures.append((symbol, sub_resource, str(exc)))
                            self.stderr.write(
                                'failed symbol={} resource={} error={}'.format(symbol, sub_resource, exc)
                            )
                    self.stdout.write('processed symbol={}'.format(symbol))
            finally:
                reset_collect_execution_context(context_token)

            self.stdout.write('updated_rows={}'.format(updated_rows))
            if failures:
                sample = ', '.join('{}:{}'.format(symbol, resource) for symbol, resource, _ in failures[:20])
                raise CommandError(
                    'Backfill finished with failures: count={} sample={}'.format(len(failures), sample)
                )


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError as exc:
        raise CommandError('Invalid --start-date, expected YYYY-MM-DD.') from exc


def resolve_symbols(symbols=None, index_code=None, all_stocks=False, limit=None):
    if symbols:
        resolved = normalize_symbols(symbols)
    elif index_code:
        resolved = resolve_index_union_symbols(index_code)
    elif all_stocks:
        resolved = resolve_all_a_stock_symbols()
    else:
        raise CommandError('Specify exactly one scope: --symbols, --index, or --all.')
    if limit is not None:
        resolved = resolved[:limit]
    if not resolved:
        raise CommandError('No symbols resolved for the requested scope.')
    return resolved


def normalize_symbols(symbols):
    return sorted({str(symbol).split('.')[0].strip() for symbol in symbols if str(symbol).strip()})


def resolve_index_union_symbols(index_code):
    with connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT DISTINCT code
                FROM saa_index_weights
                WHERE `index` = %s
                ORDER BY code
            """,
            [index_code],
        )
        return [row[0] for row in cursor.fetchall()]


def resolve_all_a_stock_symbols():
    with connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT symbol
                FROM saa_stocks
                WHERE type = 'STOCK'
                  AND market = 'A'
                ORDER BY symbol
            """
        )
        return [row[0] for row in cursor.fetchall()]


def query_statement_disclosure_records(service, sub_resource, table, symbol, start_date):
    fields = service.build_fields(table, sub_resource=sub_resource)
    raw_records = service.query_record(
        sub_resource,
        symbol,
        fields=fields,
        start_date=service.build_date_param(start_date),
    )
    records = service.transform_records(raw_records, table)
    return [
        {
            'symbol': record.get('symbol'),
            'report_date': record.get('report_date'),
            'disclosure_date': record.get('disclosure_date'),
        }
        for record in records
        if record.get('symbol') and record.get('report_date') and record.get('disclosure_date')
    ]


def apply_rate_limit_override(service, rate_limit):
    if not rate_limit:
        return
    if rate_limit <= 0:
        raise CommandError('--rate-limit must be positive.')
    service.pro.interval = round(60.0 / float(rate_limit), 3)
    service._logger.info(
        'Overriding Tushare rate limit for disclosure backfill: rate_limit=%s interval=%.3fs',
        rate_limit,
        service.pro.interval,
    )


def update_disclosure_dates(table, records):
    if not records:
        return 0
    with connection.cursor() as cursor:
        updated = 0
        for record in records:
            cursor.execute(
                """
                    UPDATE {}
                    SET disclosure_date = %s
                    WHERE symbol = %s
                      AND report_date = %s
                      AND (disclosure_date IS NULL OR disclosure_date <> %s)
                """.format(quote_identifier(table)),
                [
                    record['disclosure_date'],
                    record['symbol'],
                    record['report_date'],
                    record['disclosure_date'],
                ],
            )
            updated += cursor.rowcount
        return updated


def quote_identifier(identifier):
    return '`{}`'.format(str(identifier).replace('`', '``'))


class quiet_database_debug_logging:
    def __enter__(self):
        self.loggers = [logging.getLogger('django.db.backends')]
        self.previous_levels = [logger.level for logger in self.loggers]
        for logger in self.loggers:
            if logger.isEnabledFor(logging.DEBUG):
                logger.setLevel(logging.WARNING)

    def __exit__(self, exc_type, exc_value, traceback):
        for logger, level in zip(self.loggers, self.previous_levels):
            logger.setLevel(level)
