"""Guarded writes for migrated daily financial versions.

Adapters must validate disclosure evidence and consolidated/YTD scope first.
The caller owns the transaction and MUST roll it back on any exception. This
module never connects, commits or publishes product caches.
"""
import json
import re
from decimal import Decimal

from mysql.connector import IntegrityError

from .financial_statement_contract import content_hash, disclosure_identity, financial_fields


class StatementVersionConflict(ValueError):
    """Unresolved content conflicts require retaining accepted data."""

    def __init__(self, message, *, issue=None):
        super().__init__(message)
        self.issue = issue


def conflict_issue(table, row, previous, *, existing=False):
    def candidate(snapshot):
        metadata = snapshot.get('source_metadata') or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return {key: metadata[key] for key in ('report_type', 'update_flag') if key in metadata}

    differences = {}
    for field in financial_fields(table):
        if row[field] == previous[field]:
            continue
        value = lambda v: None if v is None else str(v)
        entry = {'existing_present': existing,
                 'existing_value': value(previous[field]) if existing else None,
                 'candidates': [dict(candidate(row), value=value(row[field]))]}
        if not existing:
            entry['candidates'].append(dict(candidate(previous), value=value(previous[field])))
            entry['candidates'].sort(key=lambda item: json.dumps(item, sort_keys=True))
        differences[field] = entry
    return dict(code='STATEMENT_VERSION_CONFLICT', provider=row['provider'],
                symbol=row['symbol'], table=table,
                report_date=row['report_date'].isoformat(),
                disclosure_date=row['disclosure_date'].isoformat(),
                differences=differences, action='REJECT_SYMBOL_BATCH')


def prepare_version(table, row):
    fields = financial_fields(table)
    allowed = set(fields) | {'symbol', 'report_date', 'disclosure_date',
                             'provider', 'source_metadata'}
    if set(row) - allowed:
        raise ValueError('Unexpected fields in financial snapshot')
    symbol, report_date, disclosure_date = disclosure_identity(row)
    if not re.fullmatch(r'[A-Za-z0-9]{1,8}', symbol) or disclosure_date < report_date:
        raise ValueError('Invalid normalized disclosure identity')
    provider = row.get('provider')
    if not isinstance(provider, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', provider):
        raise ValueError('Invalid provider identifier')
    metadata = row.get('source_metadata')
    if metadata is not None:
        keys = {'upstream', 'endpoint', 'report_type', 'client_version', 'update_flag', 'omitted_fields'}
        if (not isinstance(metadata, dict) or set(metadata) - keys
                or any(not isinstance(value, str) or not value.strip() or len(value) > 256
                       for key, value in metadata.items() if key != 'omitted_fields')):
            raise ValueError('Invalid source metadata; only bounded provenance fields are allowed')
        omitted = metadata.get('omitted_fields', [])
        if (not isinstance(omitted, list) or len(omitted) > len(fields)
                or any(not isinstance(field, str) or field not in fields for field in omitted)
                or len(set(omitted)) != len(omitted)
                or any(row.get(field) is not None for field in omitted)):
            raise ValueError('Invalid omitted financial fields')
        metadata = json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    fingerprint = content_hash(table, row)
    result = dict(symbol=symbol, report_date=report_date, disclosure_date=disclosure_date,
                  provider=provider, source_metadata=metadata, content_hash=fingerprint)
    result.update((field, None if row[field] is None else Decimal(str(row[field]))) for field in fields)
    return result


def _check_unique_keys(cursor, table):
    # Both constraints are required; retaining the old key would lose revisions.
    cursor.execute('SHOW INDEX FROM `{}`'.format(table))
    unique = {}
    for index in cursor.fetchall():
        if not index['Non_unique']:
            if index.get('Sub_part') is not None:
                raise ValueError('Prefix unique keys are not supported for version writes')
            unique.setdefault(index['Key_name'], []).append(
                (index['Seq_in_index'], index['Column_name']))
    keys = {name: tuple(field for _, field in sorted(parts)) for name, parts in unique.items()}
    expected = ('symbol', 'report_date', 'disclosure_date')
    if (keys.get('PRIMARY') != ('id',) or expected not in keys.values()
            or any(key not in {('id',), expected} for key in keys.values())):
        raise ValueError('Financial table has not passed the daily-version key migration')


def write_versions(connection, table, rows):
    """Insert snapshots; validated Tushare snapshots may replace the same daily id.

    On failure, roll back the entire caller transaction, including prior rows.
    Duplicate-key conflicts, lock timeouts and deadlocks must never be retried
    as unconditional updates. Retry the complete transaction where appropriate.
    """
    prepared = sorted([prepare_version(table, row) for row in rows],
                      key=lambda row: (row['symbol'], row['report_date'], row['disclosure_date']))
    if not connection.in_transaction or connection.autocommit:
        raise ValueError('Version writes require an explicit caller-owned transaction')
    if not prepared:
        return []
    fields = financial_fields(table)
    columns = tuple(prepared[0])
    insert_sql = 'INSERT INTO `{}` ({}) VALUES ({})'.format(
        table, ','.join('`{}`'.format(column) for column in columns),
        ','.join(['%s'] * len(columns)))
    select_sql = ('SELECT id,content_hash,{} FROM `{}` WHERE symbol=%s '
                  'AND report_date=%s AND disclosure_date=%s FOR UPDATE').format(
                      ','.join('`{}`'.format(field) for field in fields), table)
    cursor = connection.cursor(dictionary=True)
    result = []
    try:
        _check_unique_keys(cursor, table)
        for row in prepared:
            try:
                cursor.execute(insert_sql, tuple(row[column] for column in columns))
            except IntegrityError as exc:
                if exc.errno != 1062:
                    raise
                # A locking current read also sees a concurrent insert that just
                # committed, even under MySQL's repeatable-read isolation.
                identity = tuple(row[key] for key in ('symbol', 'report_date', 'disclosure_date'))
                cursor.execute(select_sql, identity)
                existing = cursor.fetchone()
                if existing is None:
                    raise StatementVersionConflict('Duplicate key without matching daily identity') from exc
                actual_hash = content_hash(table, existing)
                if existing['content_hash'] != actual_hash:
                    raise StatementVersionConflict('Stored financial content hash mismatch') from exc
                if actual_hash != row['content_hash']:
                    metadata = json.loads(row['source_metadata'] or '{}')
                    # The adapter resolves same-response candidates. update_flag
                    # is not permission to replace a previously stored snapshot.
                    if row['provider'] == 'tushare' and metadata.get('report_type') in {'1', '4', '5'}:
                        audit = conflict_issue(table, row, existing, existing=True)
                        audit.update(code='STATEMENT_VERSION_REPLACED', action='REPLACE_SAME_DAY',
                                     previous_hash=actual_hash, content_hash=row['content_hash'])
                        mutable = ('provider', 'source_metadata', 'content_hash') + tuple(fields)
                        cursor.execute(
                            'UPDATE `{}` SET {} WHERE id=%s AND content_hash=%s'.format(
                                table, ','.join('`{}`=%s'.format(field) for field in mutable)),
                            tuple(row[field] for field in mutable) + (existing['id'], actual_hash))
                        result.append({'id': existing['id'], 'created': False,
                                       'updated': True, 'audit': audit})
                        continue
                    raise StatementVersionConflict(
                        '{} {} {} {} has conflicting content'.format(table, *identity),
                        issue=conflict_issue(table, row, existing, existing=True)) from exc
                result.append({'id': existing['id'], 'created': False})
            else:
                result.append({'id': cursor.lastrowid, 'created': True})
        return result
    finally:
        cursor.close()
