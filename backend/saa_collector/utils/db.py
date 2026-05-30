# -*- coding: utf-8 -*-
import copy
import logging
from datetime import datetime

import pandas as pd


class DB(object):
    def __init__(self):
        self._logger = logging.getLogger()

    def to_sql(self, rows, con, table, primary_keys):
        if len(rows) == 0:
            return
        fields = list(rows[0].keys())
        normal_fields = copy.deepcopy(fields)
        if isinstance(primary_keys, str):
            normal_fields.remove(primary_keys)
        elif isinstance(primary_keys, list):
            normal_fields = [f for f in normal_fields if f not in primary_keys]
        update_statements = []
        for field in normal_fields:
            quoted_field = self.quote_identifier(field)
            update_statements.append("{} = VALUES({})".format(quoted_field, quoted_field))
        update_statement = ", ".join(update_statements)
        sql = "INSERT INTO {} ({}) VALUES ({}) ON DUPLICATE KEY UPDATE {}".format(
            self.quote_table_name(table),
            ", ".join(self.quote_identifier(field) for field in fields),
            ", ".join(["%s"] * len(fields)),
            update_statement
        )
        cursor = con.cursor(prepared=True)
        try:
            for stock_info in rows:
                try:
                    values = stock_info.values()
                    values = [None if pd.isna(v) else str(v) for v in values]
                    cursor.execute(sql, tuple(values))
                except:
                    self._logger.info("Failed to save %s", stock_info)
                    raise
            con.commit()
        finally:
            cursor.close()

    def to_value(self, value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.strftime('%Y%m%d')
        return value

    def quote_table_name(self, table):
        return '.'.join(self.quote_identifier(part) for part in str(table).split('.'))

    def quote_identifier(self, identifier):
        identifier = str(identifier)
        if identifier.startswith('`') and identifier.endswith('`'):
            return identifier
        return '`{}`'.format(identifier.replace('`', '``'))
