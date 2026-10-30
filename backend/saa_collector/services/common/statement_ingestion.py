"""Explicit source-version activation and transaction-owned bundle writes."""
import logging
import json

import mysql.connector

from .statement_version_writer import prepare_version, write_versions
from .statement_locks import statement_locks


def version_ingestion_enabled(config):
    enabled = config.get('saa_collector', {}).get('statement_versioning', {}).get('enabled', False)
    if type(enabled) is not bool:
        raise ValueError('statement_versioning.enabled must be a boolean')
    return enabled


def save_version_bundle(db_config, bundle):
    """Write all supplied tables atomically, never publish a partial bundle."""
    if not bundle or any(not rows for rows in bundle.values()):
        raise ValueError('Refusing empty financial version bundle')
    for table, rows in bundle.items():
        for row in rows:
            prepare_version(table, row)
    connection = mysql.connector.connect(**db_config)
    try:
        connection.autocommit = False
        symbols = [row['symbol'] for rows in bundle.values() for row in rows]
        with statement_locks(connection, symbols):
            connection.start_transaction()
            try:
                result = {table: write_versions(connection, table, bundle[table]) for table in sorted(bundle)}
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        logging.getLogger(__name__).info(
            'Financial version bundle committed: tables=%d rows=%d created=%d',
            len(result), sum(len(rows) for rows in result.values()),
            sum(row['created'] for rows in result.values() for row in rows))
        for rows in result.values():
            for row in rows:
                if row.get('updated'):
                    logging.getLogger(__name__).warning(
                        'Financial same-day replacement committed: %s',
                        json.dumps(row['audit'], sort_keys=True))
        return result
    finally:
        connection.close()
