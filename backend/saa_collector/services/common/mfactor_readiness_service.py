# -*- coding: utf-8 -*-
from django.db import connection as django_connection

from saa_collector.utils.db import DB


MFACTOR_SOURCE_REQUIREMENTS = [
    {'name': 'Trading calendar', 'object': 'saa_trade_days', 'date_column': 'date'},
    {'name': 'Security master', 'object': 'saa_securities'},
    {'name': 'Monthly historical prices', 'object': 'saa_prices_ex', 'date_column': 'date'},
    {'name': 'Stock status metadata', 'object': 'saa_extras', 'date_column': 'date'},
    {'name': 'Index quotes', 'object': 'saa_index_quotes', 'date_column': 'date'},
    {'name': 'Index constituents and weights', 'object': 'saa_index_weights', 'date_column': 'date'},
    {'name': 'Industry dictionary', 'object': 'saa_industries'},
    {'name': 'Industry constituents', 'object': 'saa_industry_stocks', 'date_column': 'date'},
    {'name': 'Combined financial statements', 'object': 'saa_financial_statements_combined', 'date_column': 'date'},
    {'name': 'Monthly prices', 'object': 'saa_monthly_prices', 'date_column': 'report_date'},
    {'name': 'Quarterly prices', 'object': 'saa_quarterly_prices', 'date_column': 'report_date'},
    {'name': 'Capital changes', 'object': 'saa_capitals', 'date_column': 'date'},
    {'name': 'Dividends', 'object': 'saa_dividends', 'date_column': 'date'},
]


class MfactorReadinessService:
    VIEW_TABLE_TYPE = 'VIEW'

    def __init__(self, connection=None, requirements=None, deep=False):
        self.connection = connection or django_connection
        self.requirements = requirements or MFACTOR_SOURCE_REQUIREMENTS
        self.deep = deep
        self.db = DB()

    def check(self):
        items = [self.check_requirement(requirement) for requirement in self.requirements]
        summary = {
            'ok': len([item for item in items if item['status'] == 'OK']),
            'error': len([item for item in items if item['status'] == 'ERROR']),
        }
        return {
            'status': 'ERROR' if summary['error'] else 'OK',
            'summary': summary,
            'items': items,
        }

    def check_requirement(self, requirement):
        object_name = requirement['object']
        with self.connection.cursor() as cursor:
            object_type = self.query_object_type(cursor, object_name)
            if object_type is None:
                return self.build_item(requirement, status='ERROR', message='object not found')

            if object_type == self.VIEW_TABLE_TYPE and not self.deep:
                return self.build_item(
                    requirement,
                    status='OK',
                    object_type=object_type,
                    message='view definition exists; data scan skipped',
                )

            if not self.object_has_rows(cursor, object_name):
                return self.build_item(
                    requirement,
                    status='ERROR',
                    object_type=object_type,
                    row_count=0,
                    max_date=None,
                    message='object is empty',
                )

            row_count = None
            max_date = None
            row_count = self.query_scalar(cursor, 'SELECT COUNT(*) FROM {}'.format(
                self.db.quote_table_name(object_name),
            ))
            date_column = requirement.get('date_column')
            if date_column:
                max_date = self.query_scalar(cursor, 'SELECT MAX({}) FROM {}'.format(
                    self.db.quote_identifier(date_column),
                    self.db.quote_table_name(object_name),
                ))

            return self.build_item(
                requirement,
                status='OK',
                object_type=object_type,
                row_count=row_count,
                max_date=max_date,
                message='',
            )

    def query_object_type(self, cursor, object_name):
        cursor.execute(
            """
            SELECT table_type
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = %s
            """,
            [object_name],
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def object_has_rows(self, cursor, object_name):
        return self.query_scalar(cursor, 'SELECT 1 FROM {} LIMIT 1'.format(
            self.db.quote_table_name(object_name),
        )) is not None

    def query_scalar(self, cursor, sql):
        cursor.execute(sql)
        row = cursor.fetchone()
        return row[0] if row else None

    def build_item(self, requirement, status, object_type=None, row_count=None, max_date=None, message=''):
        return {
            'status': status,
            'name': requirement['name'],
            'object': requirement['object'],
            'object_type': object_type,
            'row_count': row_count,
            'max_date': self.format_value(max_date),
            'message': message,
        }

    def format_value(self, value):
        if hasattr(value, 'isoformat'):
            return value.isoformat()
        return value
