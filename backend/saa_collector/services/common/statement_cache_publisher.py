"""Publish integrated and TTM candidates in one serialized transaction.

Unknown withdrawals and missing TTM dependencies fail closed. This does not
authorize deletion or modify the legacy quarterly/null arithmetic. Full-market
callers must enumerate securities and publish one bounded scope at a time.
"""
import re
import logging
from datetime import date

from .financial_statement_contract import financial_fields, is_standard_quarter
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


def build_cache_candidates(service, symbol, rows, dividends, existing, *, issues=None):
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
    standard_periods = {p for p in periods if is_standard_quarter(p)}
    if not standard_periods:
        return candidates, []
    target = max(standard_periods)
    input_start = date(target.year - 1, 1, 1)
    ttm_inputs = [row for row in candidates if input_start <= row['report_date'] <= target and is_standard_quarter(row['report_date'])]
    ttm, missing = service.build_ttm_candidates(ttm_inputs, NON_BALANCE_FIELDS)
    if missing:
        annual_date = date(target.year - 1, 12, 31)
        same_period = date(target.year - 1, target.month, target.day)
        annual = next((r for r in ttm_inputs if r['report_date'] == annual_date), None)
        diagnostic = dict(provider='tushare', symbol=symbol, table='saa_ttm_reports_cache',
            report_date=target.isoformat(), differences={
                'annual_report_date': {'value': annual_date.isoformat()},
                'missing_report_dates': {'value': [p.isoformat() for p in
                    (annual_date, same_period) if p not in standard_periods]}})
        if annual is None:
            diagnostic.update(code='STATEMENT_TTM_MISSING_ANNUAL', action='RETAIN_EXISTING_CONTINUE')
            ttm = []
        else:
            # Flow totals use the complete annual row; current balance-sheet
            # values and target metadata remain those of the latest quarter.
            fallback = dict(next(r for r in ttm_inputs if r['report_date'] == target))
            fallback.update({field: annual[field] for field in NON_BALANCE_FIELDS})
            ttm = [fallback]
            diagnostic.update(code='STATEMENT_TTM_ANNUAL_FALLBACK', action='ANNUAL_TTM_CONTINUE')
        if issues is not None:
            issues.append(diagnostic)
    elif len(ttm) != 1:
        raise ValueError('Invalid TTM candidate count')
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
            issues = []
            integrated, ttm = build_cache_candidates(service, symbol, rows, dividends, existing, issues=issues)
            writer = DB()
            writer.to_sql(integrated, connection, 'saa_integrated_reports_cache',
                          ['symbol', 'report_date'], commit=False)
            if ttm:
                writer.to_sql(ttm, connection, 'saa_ttm_reports_interface', 'symbol', commit=False)
            connection.commit()
            current_periods = {r['report_date'] for r in integrated}
            for old in existing:
                if old['report_date'] not in current_periods:
                    issues.append(dict(code='STATEMENT_CACHE_PERIOD_RETAINED', provider='tushare',
                        symbol=symbol, table='saa_integrated_reports_cache',
                        report_date=old['report_date'].isoformat(), action='RETAIN_EXISTING_CONTINUE'))
            if not ttm and not any(i['code'] == 'STATEMENT_TTM_MISSING_ANNUAL' for i in issues):
                issues.append(dict(code='STATEMENT_NO_STANDARD_TTM_INPUT', provider='tushare',
                    symbol=symbol, table='saa_ttm_reports_cache', action='RETAIN_EXISTING_CONTINUE'))
            for issue in issues:
                logging.getLogger(__name__).warning('Financial cache quality diagnostic: %s', issue)
            return {'symbol': symbol, 'integrated_rows': len(integrated), 'ttm_rows': len(ttm), 'issues': issues}
        except BaseException:
            connection.rollback()
            raise
        finally:
            cursor.close()
