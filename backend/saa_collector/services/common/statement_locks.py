"""Session locks shared by version writers and both-cache publishers."""
from contextlib import contextmanager
import hashlib
import re


@contextmanager
def statement_locks(connection, symbols):
    symbols = sorted(set(symbols))
    if not symbols or any(not isinstance(s, str) or not re.fullmatch(r'\d{6}', s) for s in symbols):
        raise ValueError('Explicit six-digit financial security scope required')
    cursor = connection.cursor()
    acquired = []
    try:
        cursor.execute('SELECT DATABASE()')
        database = cursor.fetchone()[0]
        if not database:
            raise ValueError('Statement locks require a selected database')
        for symbol in symbols:
            name = 'saa:statement:' + hashlib.sha256((database + ':' + symbol).encode()).hexdigest()[:40]
            cursor.execute('SELECT GET_LOCK(%s,5)', (name,))
            if cursor.fetchone()[0] != 1:
                raise TimeoutError('Financial publication lock unavailable for ' + symbol)
            acquired.append(name)
        yield
    finally:
        try:
            for name in reversed(acquired):
                cursor.execute('SELECT RELEASE_LOCK(%s)', (name,))
                cursor.fetchone()
        finally:
            cursor.close()
