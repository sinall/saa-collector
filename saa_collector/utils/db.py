# -*- coding: utf-8 -*-
import copy
import logging


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
            update_statements.append("{} = VALUES({})".format(field, field))
        update_statement = ", ".join(update_statements)
        sql = "INSERT INTO {} ({}) VALUES ({}) ON DUPLICATE KEY UPDATE {}".format(
            table, ", ".join(fields), ", ".join(["%s"] * len(fields)), update_statement
        )
        cursor = con.cursor(prepared=True)
        for stock_info in rows:
            try:
                values = stock_info.values()
                values = [None if v is None else str(v) for v in values]
                cursor.execute(sql, tuple(values))
            except:
                self._logger.info("Failed to save %s", stock_info)
                raise
        con.commit()
