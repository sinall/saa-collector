"""Explicit shadow copy for a reviewed, quiesced financial migration.

No connections, schema changes, renames or task scheduling are performed here.
The operator must stop source writers, own the empty shadow and retain a tested
backup. This owns one DML transaction; batch size bounds memory, not commits.
It cannot establish historical disclosure evidence or prevent external SQL.
"""
import hashlib
import json

from .financial_statement_contract import content_hash, financial_fields
from .statement_legacy_guard import assert_legacy_write_allowed
from .statement_migration_plan import legacy_snapshot
from .statement_version_writer import _check_unique_keys


def _pages(cursor, table, batch_size):
    last = None
    while True:
        # MySQL 8.0 may scan the whole prefix for a row-constructor inequality.
        where = ' WHERE symbol > %s OR (symbol=%s AND report_date > %s)' if last else ''
        cursor.execute('SELECT * FROM `{}`{} ORDER BY symbol,report_date LIMIT %s'.format(table, where),
                       (last[0], *last, batch_size) if last else (batch_size,))
        rows = cursor.fetchall()
        if not rows:
            return
        yield rows
        last = (rows[-1]['symbol'], rows[-1]['report_date'])


def _add_digest(digest, row, fingerprint):
    payload = [row['symbol'], row['report_date'].isoformat(),
               row['disclosure_date'].isoformat(), fingerprint]
    digest.update(json.dumps(payload, ensure_ascii=True, separators=(',', ':')).encode())
    digest.update(b'\n')


def verify_legacy_shadow(connection, table, receipt, *, batch_size=1000):
    """Read-only revalidation against the copy receipt immediately before DDL.

    Does not replace draining writers: changes after this snapshot still require
    the operator's exclusive maintenance window. No connection or DDL is owned.
    """
    financial_fields(table)
    if type(batch_size) is not int or not 1 <= batch_size <= 10000:
        raise ValueError('batch_size must be between 1 and 10000')
    if connection.in_transaction or connection.autocommit:
        raise ValueError('Verification requires an idle non-autocommit connection')
    shadow = table + '_pit_shadow'
    if receipt.get('table') != table or receipt.get('shadow') != shadow:
        raise ValueError('Copy receipt scope mismatch')
    cursor = connection.cursor(dictionary=True)
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ', readonly=True)
        verified = dict(table=table, shadow=shadow)
        for name, key in ((table, 'source_digest'), (shadow, 'shadow_digest')):
            digest, count = hashlib.sha256(), 0
            cursor.execute('SELECT COUNT(*) AS n FROM `{}`'.format(name))
            expected_count = cursor.fetchone()['n']
            for rows in _pages(cursor, name, batch_size):
                for row in rows:
                    if name == table:
                        row = legacy_snapshot(table, row)
                    fingerprint = content_hash(table, row)
                    if (fingerprint != row['content_hash'] or row['provider'] != 'unknown'
                            or row['source_metadata'] is not None):
                        raise ValueError('Shadow content/provenance changed since copy')
                    _add_digest(digest, row, fingerprint)
                    count += 1
            if count != expected_count or count != receipt.get('rows'):
                raise ValueError('Migration row count changed since copy')
            verified[key] = digest.hexdigest()
            verified['rows'] = count
        if verified != receipt or verified['source_digest'] != verified['shadow_digest']:
            raise ValueError('Migration content digest mismatch since copy')
        connection.commit()
        return verified
    except BaseException:
        connection.rollback()
        raise
    finally:
        cursor.close()


def copy_legacy_to_shadow(connection, table, *, batch_size=1000):
    fields = financial_fields(table)
    if type(batch_size) is not int or not 1 <= batch_size <= 10000:
        raise ValueError('batch_size must be between 1 and 10000')
    if connection.in_transaction or connection.autocommit:
        raise ValueError('Shadow copy requires an idle non-autocommit connection')
    shadow = table + '_pit_shadow'
    legacy_columns = ['symbol', 'report_date', 'disclosure_date', *fields]
    version_columns = ['id', 'symbol', 'report_date', 'disclosure_date',
                       'provider', 'source_metadata', 'content_hash', *fields]
    plain = connection.cursor()
    reader = connection.cursor(dictionary=True)
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ')
        assert_legacy_write_allowed(plain, table)
        definitions = {}
        for name, expected in ((table, legacy_columns), (shadow, version_columns)):
            plain.execute('SHOW COLUMNS FROM `{}`'.format(name))
            columns = plain.fetchall()
            if [column[0] for column in columns] != expected:
                raise ValueError('Unreviewed column contract: ' + name)
            definitions[name] = {column[0]: column[1:3] for column in columns}
        for name in ['symbol', 'report_date', *fields]:
            if definitions[table][name] != definitions[shadow][name]:
                raise ValueError('Shadow changed financial/identity column: ' + name)
        if definitions[shadow]['disclosure_date'] != ('date', 'NO'):
            raise ValueError('Shadow disclosure date must be non-null DATE')
        _check_unique_keys(reader, shadow)
        plain.execute('SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES '
                      'WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN (%s,%s)', (table, shadow))
        engines = dict(plain.fetchall())
        if engines != {table: 'InnoDB', shadow: 'InnoDB'}:
            raise ValueError('Both migration tables must use InnoDB')
        plain.execute('SELECT COUNT(*) FROM `{}`'.format(shadow))
        if plain.fetchone()[0]:
            raise ValueError('Shadow is not empty; refusing append or overwrite')
        source_digest = hashlib.sha256()
        count = 0
        insert_columns = version_columns[1:]
        insert_sql = 'INSERT INTO `{}` ({}) VALUES ({})'.format(
            shadow, ','.join('`{}`'.format(name) for name in insert_columns),
            ','.join(['%s'] * len(insert_columns)))
        for rows in _pages(reader, table, batch_size):
            prepared = [legacy_snapshot(table, row) for row in rows]
            plain.executemany(insert_sql, [tuple(row[name] for name in insert_columns)
                                          for row in prepared])
            for row in prepared:
                _add_digest(source_digest, row, row['content_hash'])
            count += len(prepared)
        shadow_digest = hashlib.sha256()
        verified = 0
        for rows in _pages(reader, shadow, batch_size):
            for row in rows:
                fingerprint = content_hash(table, row)
                if (fingerprint != row['content_hash'] or row['provider'] != 'unknown'
                        or row['source_metadata'] is not None):
                    raise ValueError('Shadow content or provenance verification failed')
                _add_digest(shadow_digest, row, fingerprint)
                verified += 1
        if verified != count or shadow_digest.digest() != source_digest.digest():
            raise ValueError('Shadow identity/content checksum mismatch')
        connection.commit()
        return dict(table=table, shadow=shadow, rows=count,
                    source_digest=source_digest.hexdigest(),
                    shadow_digest=shadow_digest.hexdigest())
    except BaseException:
        connection.rollback()
        raise
    finally:
        reader.close()
        plain.close()
