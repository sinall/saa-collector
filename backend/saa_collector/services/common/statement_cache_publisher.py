"""Publish integrated and TTM candidates in one serialized transaction.

Unknown withdrawals and missing TTM dependencies fail closed. This does not
authorize deletion or modify the legacy quarterly/null arithmetic. Full-market
callers must enumerate securities and publish one bounded scope at a time.
"""
import re

from .financial_statement_contract import financial_fields
from .statement_locks import statement_locks
from saa_collector.utils.db import DB


NON_BALANCE_FIELDS = (
    *financial_fields('saa_raw_income_statement'),
    *financial_fields('saa_raw_cash_flow_statement'),
)
CACHE_COLUMNS = (
    'symbol', 'report_date', 'disclosure_date', 'name', 'market', 'exchange',
    'board', 'industry_classification_id', 'industry_classification_name', 'price',
    *financial_fields('saa_raw_balance_sheet'), *NON_BALANCE_FIELDS, 'dividend',
)


def build_cache_candidates(service, symbol, rows, dividends, existing, cutoff):
    if not rows:
        raise ValueError('Empty financial candidate is not a withdrawal')
    years = {}
    for dividend in dividends:
        year = dividend['year']
        if year in years:
            raise ValueError('Duplicate yearly dividend candidate')
        years[year] = dividend['dividend']
    candidates, periods = [], set()
    for source in rows:
        if set(source) != set(CACHE_COLUMNS) or source['symbol'] != symbol:
            raise ValueError('Financial cache column/scope mismatch')
        row = dict(source)
        # Preserve the existing VARCHAR(2) product-cache codes, including SS
        # for SSE. Canonical exchange-code migration is a separate change.
        exchange = row['exchange']
        if exchange not in {None, 'SH', 'SS', 'SZ', 'BJ', 'HK', 'SSE', 'SZSE'}:
            raise ValueError('Unknown cache exchange: {}'.format(exchange))
        row['exchange'] = {'SSE': 'SS', 'SZSE': 'SZ'}.get(exchange, exchange)
        period = row['report_date']
        if period in periods:
            raise ValueError('Duplicate report period in financial candidate')
        periods.add(period)
        if period.year in years:
            row['dividend'] = years[period.year]
        candidates.append(row)
    if {row['report_date'] for row in existing} - periods:
        raise ValueError('Unreviewed financial withdrawal; retaining both caches')
    recent = [row for row in candidates if row['report_date'] >= cutoff]
    ttm, missing = service.build_ttm_candidates(recent, NON_BALANCE_FIELDS)
    if missing or len(ttm) != 1:
        raise ValueError('Missing TTM dependencies; retaining both caches')
    return candidates, ttm


def publish_statement_caches(connection, service, symbol):
    if not isinstance(symbol, str) or not re.fullmatch(r'\d{6}', symbol):
        raise ValueError('One explicit financial security is required')
    if connection.autocommit or connection.in_transaction:
        raise ValueError('Publisher requires an idle non-autocommit connection')
    # Lock before acquiring the consistent read view, preventing a slower older
    # publisher from overwriting a newer committed batch.
    with statement_locks(connection, [symbol]):
        cursor = connection.cursor(dictionary=True)
        try:
            connection.start_transaction(isolation_level='REPEATABLE READ')
            expressions = []
            for column in CACHE_COLUMNS:
                if column in {'report_date', 'disclosure_date'}:
                    expressions.append('c.`{0}` AS `{0}`'.format(column))
                else:
                    expressions.append('ir.`{}`'.format(column))
            cursor.execute(
                'SELECT {} FROM saa_integrated_reports_impl ir '
                'JOIN saa_financial_statements_combined c '
                'ON c.symbol=ir.symbol AND c.report_date=ir.`date` '
                'WHERE ir.symbol=%s ORDER BY c.report_date'.format(','.join(expressions)), (symbol,))
            rows = cursor.fetchall()
            # Same annual sum as the legacy view, without its derived date
            # expression that MySQL rejects under ONLY_FULL_GROUP_BY.
            cursor.execute('SELECT YEAR(`date`) AS year,SUM(dividend) AS dividend '
                           'FROM saa_dividends WHERE symbol=%s GROUP BY YEAR(`date`)', (symbol,))
            dividends = cursor.fetchall()
            cursor.execute('SELECT report_date FROM saa_integrated_reports_cache WHERE symbol=%s', (symbol,))
            existing = cursor.fetchall()
            cursor.execute('SELECT DATE_SUB(CURDATE(), INTERVAL 4 YEAR) AS cutoff')
            cutoff = cursor.fetchone()['cutoff']
            integrated, ttm = build_cache_candidates(service, symbol, rows, dividends, existing, cutoff)
            writer = DB()
            writer.to_sql(integrated, connection, 'saa_integrated_reports_cache',
                          ['symbol', 'report_date'], commit=False)
            writer.to_sql(ttm, connection, 'saa_ttm_reports_interface', 'symbol', commit=False)
            connection.commit()
            return {'symbol': symbol, 'integrated_rows': len(integrated), 'ttm_rows': len(ttm)}
        except BaseException:
            connection.rollback()
            raise
        finally:
            cursor.close()
