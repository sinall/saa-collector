"""Explicit financial columns, frozen from the reviewed legacy schema.

Adding a metadata column must never expand the arithmetic field set.
Changes to this manifest require review of financial meaning and hash inputs.
"""
import json
from pathlib import Path

_FIELDS = json.loads(Path(__file__).with_name('financial_statement_fields.json').read_text())


def financial_fields(table):
    """Return a fresh immutable field sequence; unknown tables fail closed."""
    return tuple(_FIELDS[table])


def financial_scale(table, field):
    """Read the reviewed SQL scale, not a provider's inferred precision."""
    import re
    match = re.fullmatch(r'decimal\(\d+,(\d+)\)', _FIELDS[table][field])
    if not match:
        raise ValueError('Unreviewed financial type')
    return int(match[1])


def disclosure_identity(row):
    """Validate already-normalized daily identity; never invent missing dates."""
    from datetime import date
    symbol = row.get('symbol')
    if not isinstance(symbol, str) or not symbol or len(symbol) > 8:
        raise ValueError('Invalid normalized security symbol')
    dates = [row.get('report_date'), row.get('disclosure_date')]
    if any(type(value) is not date for value in dates):
        raise ValueError('Report and disclosure dates must be normalized dates')
    return symbol, *dates


def content_hash(table, row):
    """Hash a complete standard financial snapshot, excluding provenance.

    Callers must distinguish omitted upstream fields before constructing the
    snapshot. Values must already fit the reviewed database precision; this
    function refuses silent rounding rather than hashing different stored data.
    """
    import hashlib
    import re
    from decimal import Decimal, InvalidOperation, localcontext

    values = []
    for field, sql_type in sorted(_FIELDS[table].items()):
        if field not in row:
            raise ValueError('Incomplete snapshot: missing {}'.format(field))
        value = row[field]
        if value is None:
            values.append([field, None])
            continue
        match = re.fullmatch(r'decimal\((\d+),(\d+)\)', sql_type)
        if not match:
            raise ValueError('Unreviewed financial type: {}'.format(sql_type))
        precision, scale = map(int, match.groups())
        try:
            with localcontext() as ctx:
                ctx.prec = max(precision + 4, 40)
                number = Decimal(str(value))
                if not number.is_finite():
                    raise ValueError('Nonfinite financial value')
                quantized = number.quantize(Decimal(1).scaleb(-scale))
                if number != quantized or abs(number) >= Decimal(10) ** (precision - scale):
                    raise ValueError('Value exceeds reviewed precision: {}'.format(field))
                encoded = format(abs(quantized) if quantized == 0 else quantized, 'f')
        except (InvalidOperation, TypeError) as exc:
            raise ValueError('Invalid financial value: {}'.format(field)) from exc
        values.append([field, encoded])
    payload = json.dumps(['financial-content-v1', table, values],
                         ensure_ascii=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def latest_view_sql(table, legacy_columns):
    """Render a read-only projection; does not connect or execute SQL.

    The migration caller supplies the verified legacy column order. Applying
    this requires the daily unique constraint and non-null disclosure dates.
    This renderer deliberately never replaces an existing object implicitly.
    """
    if table not in _FIELDS:
        raise ValueError('Unknown statement table')
    identity = {'symbol', 'report_date', 'disclosure_date'}
    columns = tuple(legacy_columns)
    allowed = identity | set(financial_fields(table))
    if (not identity.issubset(columns) or len(set(columns)) != len(columns)
            or any(column not in allowed for column in columns)):
        raise ValueError('Invalid legacy projection columns')
    view = table.replace('saa_raw_', 'saa_latest_', 1)
    selected = ', '.join('r.`{}`'.format(column) for column in columns)
    return (
        'CREATE VIEW `{view}` AS SELECT {selected} FROM `{table}` r '
        'JOIN (SELECT symbol, report_date, MAX(disclosure_date) AS disclosure_date '
        'FROM `{table}` GROUP BY symbol, report_date) latest '
        'ON r.symbol = latest.symbol AND r.report_date = latest.report_date '
        'AND r.disclosure_date = latest.disclosure_date'
    ).format(view=view, selected=selected, table=table)
