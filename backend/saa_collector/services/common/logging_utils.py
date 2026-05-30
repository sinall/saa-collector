# -*- coding: utf-8 -*-
from datetime import date, datetime


def format_sample_record(records):
    if not records:
        return None
    return {
        key: format_log_value(value)
        for key, value in records[0].items()
    }


def format_log_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
