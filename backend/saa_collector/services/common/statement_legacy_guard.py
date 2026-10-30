"""Fail closed for old report-period writers after the version schema expands.

This is not a migration lock. Operators must stop and drain old writers before
DDL; a schema check alone cannot prevent a concurrent check/cutover race.
"""
import re

STATEMENT_TABLES = frozenset({
    'saa_raw_balance_sheet', 'saa_raw_income_statement', 'saa_raw_cash_flow_statement',
})


def guard_legacy_connection(connection, table):
    if str(table).replace('`', '').split('.')[-1] not in STATEMENT_TABLES:
        return
    cursor = connection.cursor()
    try:
        assert_legacy_write_allowed(cursor, table)
    finally:
        cursor.close()


def assert_legacy_write_allowed(cursor, table):
    parts = str(table).replace('`', '').split('.')
    if parts[-1] not in STATEMENT_TABLES:
        return
    if len(parts) > 2 or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', p) for p in parts):
        raise ValueError('Invalid financial table name')
    quoted = '.'.join('`{}`'.format(p) for p in parts)
    cursor.execute('SHOW COLUMNS FROM ' + quoted)
    fields = {row[0] for row in cursor.fetchall()}
    if fields & {'id', 'provider', 'source_metadata', 'content_hash'}:
        raise ValueError('Legacy financial writes are disabled for the version schema; '
                         'use the validated version writer, not report-period upsert/backfill')
    cursor.execute('SHOW INDEX FROM ' + quoted)
    primary = tuple(name for _, name in sorted(
        (row[3], row[4]) for row in cursor.fetchall() if row[2] == 'PRIMARY'))
    if primary != ('symbol', 'report_date'):
        raise ValueError('Unrecognized financial primary key; legacy writes refused')
