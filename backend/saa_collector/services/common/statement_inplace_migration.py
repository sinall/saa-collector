"""Explicit, connection-injected migration helpers; never open a database.

Run only with drained writers and verified backups. Receipts must be captured
before expansion and retained outside the database. No DDL or financial-value
updates occur here. Each table backfill owns one transaction, not one per page.
"""
import hashlib

from .financial_statement_contract import content_hash, disclosure_identity, financial_fields
from .statement_shadow_copy import _add_digest, _pages


def _write_hash_batch(cursor, table, updates):
    financial_fields(table)
    if not updates:
        return
    # Connector executemany batches INSERT, but sends UPDATE once per row.
    cases = ' '.join('WHEN %s THEN %s' for _ in updates)
    ids = ','.join('%s' for _ in updates)
    params = tuple(value for fingerprint, row_id in updates for value in (row_id, fingerprint))
    params += tuple(row_id for _, row_id in updates)
    cursor.execute('UPDATE `{}` SET content_hash=CASE id {} END '
                   'WHERE id IN ({}) AND content_hash IS NULL'.format(table, cases, ids), params)
    if cursor.rowcount != len(updates):
        raise ValueError('Unexpected backfill update count')


def _scan(connection, table, receipt=None, *, backfill=False, batch_size=1000):
    fields = financial_fields(table)
    if type(batch_size) is not int or not 1 <= batch_size <= 10000:
        raise ValueError('Invalid batch_size')
    if connection.in_transaction or connection.autocommit:
        raise ValueError('Requires an idle non-autocommit connection')
    if receipt is not None and receipt.get('table') != table:
        raise ValueError('Receipt scope mismatch')
    reader = connection.cursor(dictionary=True)
    writer = connection.cursor()
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ', readonly=not backfill)
        reader.execute('SHOW COLUMNS FROM `{}`'.format(table))
        expected = ['symbol', 'report_date', 'disclosure_date', *fields]
        if receipt is not None:
            expected = ['id', *expected[:3], 'provider', 'source_metadata', 'content_hash', *fields]
        if [row['Field'] for row in reader.fetchall()] != expected:
            raise ValueError('Unreviewed column contract')
        reader.execute('SELECT COUNT(*) AS n FROM `{}`'.format(table))
        count = reader.fetchone()['n']
        reader.execute('SELECT 1 FROM `{}` GROUP BY symbol,report_date HAVING COUNT(*) > 1 LIMIT 1'.format(table))
        if reader.fetchone():
            raise ValueError('Multiple versions: legacy migration/recovery forbidden')
        digest, seen = hashlib.sha256(), 0
        for rows in _pages(reader, table, batch_size):
            updates = []
            for row in rows:
                disclosure_identity(row)
                fingerprint = content_hash(table, row)
                if receipt is not None:
                    if row['provider'] != 'unknown' or row['source_metadata'] is not None:
                        raise ValueError('Ingestion metadata found; migration/recovery forbidden')
                    if row['content_hash'] != fingerprint:
                        if not backfill or row['content_hash'] is not None:
                            raise ValueError('Stored hash does not match financial values')
                        updates.append((fingerprint, row['id']))
                _add_digest(digest, row, fingerprint)
                seen += 1
            if updates:
                _write_hash_batch(writer, table, updates)
        result = dict(table=table, rows=seen, digest=digest.hexdigest())
        if seen != count or (receipt is not None and result != receipt):
            raise ValueError('Original identity/content receipt mismatch')
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        reader.close()
        writer.close()


def legacy_receipt(connection, table, *, batch_size=1000):
    return _scan(connection, table, batch_size=batch_size)


def backfill_legacy_inplace(connection, table, receipt, *, batch_size=1000):
    return _scan(connection, table, receipt, backfill=True, batch_size=batch_size)


def verify_inplace(connection, table, receipt, *, batch_size=1000):
    return _scan(connection, table, receipt, batch_size=batch_size)
