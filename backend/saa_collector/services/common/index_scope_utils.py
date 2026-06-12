# -*- coding: utf-8 -*-
from datetime import date as date_type, datetime


def coerce_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_type):
        return value
    return datetime.strptime(str(value), '%Y-%m-%d').date()


def resolve_index_constituents_by_dates(cursor, index_code, target_dates):
    return {
        target_date: payload[1]
        for target_date, payload in resolve_index_constituent_payloads_by_dates(cursor, index_code, target_dates).items()
    }


def resolve_index_constituent_payloads_by_dates(cursor, index_code, target_dates):
    normalized_dates = sorted({coerce_date(value) for value in target_dates if value})
    normalized_dates = [value for value in normalized_dates if value]
    if not index_code or not normalized_dates:
        return {}

    max_target_date = normalized_dates[-1]
    cursor.execute(
        """
            SELECT DISTINCT date
            FROM saa_index_weights
            WHERE `index` = %s
              AND date <= %s
            ORDER BY date
        """,
        [index_code, max_target_date],
    )
    index_dates = [coerce_date(row[0]) for row in cursor.fetchall()]
    if not index_dates:
        return {target_date: (None, set()) for target_date in normalized_dates}

    selected_index_date_by_target = {}
    index_pos = 0
    for target_date in normalized_dates:
        while index_pos + 1 < len(index_dates) and index_dates[index_pos + 1] <= target_date:
            index_pos += 1
        if index_dates[index_pos] <= target_date:
            selected_index_date_by_target[target_date] = index_dates[index_pos]

    selected_index_dates = sorted(set(selected_index_date_by_target.values()))
    if not selected_index_dates:
        return {target_date: (None, set()) for target_date in normalized_dates}

    placeholders = ','.join(['%s'] * len(selected_index_dates))
    cursor.execute(
        f"""
            SELECT date, code
            FROM saa_index_weights
            WHERE `index` = %s
              AND date IN ({placeholders})
        """,
        [index_code] + selected_index_dates,
    )

    constituents_by_index_date = {}
    for index_date, code in cursor.fetchall():
        constituents_by_index_date.setdefault(coerce_date(index_date), set()).add(code)

    return {
        target_date: (
            selected_index_date_by_target.get(target_date),
            set(constituents_by_index_date.get(selected_index_date_by_target.get(target_date), set())),
        )
        for target_date in normalized_dates
    }


def resolve_index_constituents_as_of(cursor, index_code, target_date):
    return resolve_index_constituents_by_dates(cursor, index_code, [target_date]).get(coerce_date(target_date), set())
