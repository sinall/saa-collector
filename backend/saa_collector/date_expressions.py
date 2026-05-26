import re
from datetime import date, datetime, timedelta


ABSOLUTE_DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
RELATIVE_T_DATE_PATTERN = re.compile(
    r'^T(?:(?P<sign>[+-])(?P<days>\d+)(?P<unit>td|d)?)?$',
    re.IGNORECASE,
)
MAX_TRADE_CALENDAR_STALENESS_DAYS = 14


def parse_schedule_date(value, *, today=None, trade_day_resolver=None):
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    base_date = today or date.today()
    lowered = text.lower()
    if lowered in ('today', 't'):
        return base_date

    if ABSOLUTE_DATE_PATTERN.fullmatch(text):
        return datetime.strptime(text, '%Y-%m-%d').date()

    match = RELATIVE_T_DATE_PATTERN.fullmatch(text)
    if not match:
        raise ValueError(f'Unsupported schedule date expression: {text}')

    sign = match.group('sign')
    if sign is None:
        return base_date

    days = int(match.group('days'))
    unit = (match.group('unit') or 'td').lower()
    offset = days if sign == '+' else -days

    if unit == 'd':
        return base_date + timedelta(days=offset)

    resolver = trade_day_resolver or resolve_trade_day_offset
    return resolver(base_date, offset)


def normalize_schedule_params(params):
    normalized = dict(params or {})

    start_value = normalized.get('start_date')
    if start_value in (None, ''):
        start_value = normalized.get('date_start')
    end_value = normalized.get('end_date')
    if end_value in (None, ''):
        end_value = normalized.get('date_end')

    if start_value not in (None, ''):
        normalized['start_date'] = start_value
    else:
        normalized.pop('start_date', None)

    if end_value not in (None, ''):
        normalized['end_date'] = end_value
    else:
        normalized.pop('end_date', None)

    normalized.pop('date_start', None)
    normalized.pop('date_end', None)

    return normalized


def validate_schedule_params(params):
    normalized = normalize_schedule_params(params)

    for key in ('start_date', 'end_date'):
        value = normalized.get(key)
        if value in (None, ''):
            continue
        parse_schedule_date(value)

    return normalized


def resolve_schedule_date_range(
    params,
    *,
    today=None,
    trade_day_resolver=None,
    trade_calendar_refresher=None,
):
    normalized = normalize_schedule_params(params)
    base_date = today or date.today()

    try:
        start_date = parse_schedule_date(
            normalized.get('start_date'),
            today=base_date,
            trade_day_resolver=trade_day_resolver,
        )
        end_date = parse_schedule_date(
            normalized.get('end_date'),
            today=base_date,
            trade_day_resolver=trade_day_resolver,
        )
    except ValueError as exc:
        if (
            trade_calendar_refresher is None
            or 'Trade calendar is stale' not in str(exc)
        ):
            raise

        latest_trade_day = get_latest_trade_day_on_or_before(base_date)
        if latest_trade_day is None:
            raise

        trade_calendar_refresher(latest_trade_day, base_date)

        start_date = parse_schedule_date(
            normalized.get('start_date'),
            today=base_date,
            trade_day_resolver=trade_day_resolver,
        )
        end_date = parse_schedule_date(
            normalized.get('end_date'),
            today=base_date,
            trade_day_resolver=trade_day_resolver,
        )
    return start_date, end_date, normalized


def resolve_trade_day_offset(base_date, offset):
    if offset == 0:
        latest_trade_day = get_latest_trade_day_on_or_before(base_date)
        if latest_trade_day is None:
            raise ValueError(f'No trade day found on or before {base_date}')
        return latest_trade_day

    latest_trade_day = get_latest_trade_day_on_or_before(base_date)
    if latest_trade_day is None:
        raise ValueError(f'No trade day found on or before {base_date}')

    if (base_date - latest_trade_day).days >= MAX_TRADE_CALENDAR_STALENESS_DAYS:
        raise ValueError(
            'Trade calendar is stale: latest trade day is {} but base date is {}'.format(
                latest_trade_day, base_date
            )
        )

    if offset < 0:
        target = get_trade_day_before_with_offset(base_date, abs(offset))
    else:
        target = get_trade_day_with_offset(latest_trade_day, abs(offset), 'next')
    if target is None:
        raise ValueError(f'No trade day found for offset {offset} from {base_date}')
    return target


def get_latest_trade_day_on_or_before(base_date):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT date FROM saa_trade_days WHERE date <= %s ORDER BY date DESC LIMIT 1',
            [base_date],
        )
        row = cursor.fetchone()
    return _coerce_db_date(row[0]) if row else None


def get_trade_day_with_offset(anchor_date, steps, direction):
    from django.db import connection

    if steps <= 0:
        return anchor_date

    if direction == 'next':
        comparator = '>'
        order = 'ASC'
    elif direction == 'previous':
        comparator = '<'
        order = 'DESC'
    else:
        raise ValueError(f'Unsupported direction: {direction}')

    query = (
        f'SELECT date FROM saa_trade_days '
        f'WHERE date {comparator} %s ORDER BY date {order} LIMIT %s'
    )
    with connection.cursor() as cursor:
        cursor.execute(query, [anchor_date, steps])
        rows = cursor.fetchall()

    if len(rows) < steps:
        return None
    return _coerce_db_date(rows[-1][0])


def get_trade_day_on_or_before_with_offset(base_date, steps):
    from django.db import connection

    if steps <= 0:
        return get_latest_trade_day_on_or_before(base_date)

    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT date FROM saa_trade_days WHERE date <= %s ORDER BY date DESC LIMIT %s',
            [base_date, steps],
        )
        rows = cursor.fetchall()

    if len(rows) < steps:
        return None
    return _coerce_db_date(rows[-1][0])


def get_trade_day_before_with_offset(base_date, steps):
    from django.db import connection

    if steps <= 0:
        return get_latest_trade_day_on_or_before(base_date)

    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT date FROM saa_trade_days WHERE date < %s ORDER BY date DESC LIMIT %s',
            [base_date, steps],
        )
        rows = cursor.fetchall()

    if len(rows) < steps:
        return None
    return _coerce_db_date(rows[-1][0])


def _coerce_db_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), '%Y-%m-%d').date()
