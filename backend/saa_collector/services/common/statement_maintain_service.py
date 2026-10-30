# -*- coding: utf-8 -*-
import copy
import datetime
import itertools

import mysql.connector

from saa_collector.services.common.config_service import ConfigService
from saa_collector.utils.db import DB
from saa_collector.services.common.financial_statement_contract import financial_fields
from saa_collector.services.common.statement_ingestion import version_ingestion_enabled
from saa_collector.services.common.statement_cache_publisher import publish_statement_caches


class StatementMaintainService:
    def __init__(self):
        super().__init__()
        self.config_service = ConfigService()
        self.db_config = self.config_service.get_db_config()

    def process(self, symbols):
        if version_ingestion_enabled(self.config_service.get_config()):
            return self.publish_caches(symbols)
        self.refresh_financial_report_cache(symbols)
        self.refresh_ttm_report_cache(symbols)

    def publish_caches(self, symbols):
        if isinstance(symbols, str):
            symbols = [symbols]
        if not symbols:
            raise ValueError('Version cache publication requires explicit securities')
        results = []
        for symbol in sorted(set(symbols)):
            connection = mysql.connector.connect(**self.db_config)
            try:
                connection.autocommit = False
                results.append(publish_statement_caches(connection, self, symbol))
            finally:
                connection.close()
        return results

    def refresh_financial_report_cache(self, symbols):
        if version_ingestion_enabled(self.config_service.get_config()):
            return self.publish_caches(symbols)
        if symbols:
            if isinstance(symbols, str):
                args = (symbols,)
            else:
                args = (','.join(symbols),)
        else:
            args = ()
        cnx = mysql.connector.connect(**self.db_config)
        cursor = None
        try:
            cursor = cnx.cursor()
            cursor.callproc('saa_refresh_integrated_reports_cache', args)
            cnx.commit()
        finally:
            if cursor:
                cursor.close()
            cnx.close()

    def refresh_ttm_report_cache(self, symbols):
        if version_ingestion_enabled(self.config_service.get_config()):
            return self.publish_caches(symbols)
        income_fields = self.get_fields("saa_raw_income_statement")
        cash_flow_fields = self.get_fields("saa_raw_cash_flow_statement")
        non_balance_sheet_fields = income_fields + cash_flow_fields

        if symbols:
            sql = "SELECT * FROM saa_integrated_reports_interface " \
                  "WHERE symbol IN (%s) AND COALESCE(report_date, date) >= DATE_SUB(CURDATE(), INTERVAL 4 YEAR)"
            if isinstance(symbols, str):
                param_count = 1
                params = (symbols,)
            else:
                param_count = len(symbols)
                params = tuple(symbols)
            sql = sql % ','.join(['%s'] * param_count)
        else:
            sql = "SELECT * FROM saa_integrated_reports_interface " \
                  "WHERE COALESCE(report_date, date) >= DATE_SUB(CURDATE(), INTERVAL 4 YEAR)"
            params = ()
        cnx = mysql.connector.connect(**self.db_config)
        cursor = None
        try:
            cursor = cnx.cursor(dictionary=True)
            cursor.execute(sql, params)
            integrated_reports, _ = self.build_ttm_candidates(
                cursor.fetchall(), non_balance_sheet_fields)

            DB().to_sql(integrated_reports, cnx, "saa_ttm_reports_interface", "symbol")
        finally:
            if cursor:
                cursor.close()
            cnx.close()

    def build_ttm_candidates(self, statements, non_balance_sheet_fields):
        """Calculate without writes; missing dependencies do not authorize deletion.

        Duplicate periods must be resolved by the version projection, never
        by input order. Keep the existing null-as-zero arithmetic unchanged.
        """
        rows = [self.normalize_report_date(dict(row)) for row in statements]
        seen = set()
        for row in rows:
            key = (row['symbol'], row['report_date'])
            if key in seen:
                raise ValueError('Duplicate statement period in cache candidate: {}'.format(key))
            seen.add(key)
        rows.sort(key=lambda row: row['symbol'])
        candidates, missing = [], []
        for symbol, group in itertools.groupby(rows, lambda row: row['symbol']):
            report = self.gen_ttm_report(group, non_balance_sheet_fields)
            if report is None:
                missing.append(symbol)
            else:
                candidates.append(report)
        return candidates, missing

    def gen_ttm_report(self, statements, non_balance_sheet_fields):
        statements = [self.normalize_report_date(statement) for statement in statements]
        statements = sorted(statements, key=lambda i: i['report_date'], reverse=True)
        latest_integrate_report = statements[0]
        if latest_integrate_report['report_date'].month == 12:
            return latest_integrate_report
        date_to_integrated_report_list = {r['report_date']: r for r in statements}
        current_quarter_report = latest_integrate_report
        current_report_date = latest_integrate_report['report_date']
        previous_year_date = datetime.date(year=current_report_date.year - 1, month=12, day=31)
        previous_quarter_date = datetime.date(
            year=current_report_date.year - 1,
            month=current_report_date.month,
            day=current_report_date.day
        )
        if not all(d in date_to_integrated_report_list.keys() for d in (previous_year_date, previous_quarter_date)):
            return
        previous_yearly_report = date_to_integrated_report_list[previous_year_date]
        previous_quarter_report = date_to_integrated_report_list[previous_quarter_date]

        integrated_report = copy.deepcopy(current_quarter_report)
        for field in non_balance_sheet_fields:
            integrated_report[field] = (previous_yearly_report[field] or 0)
            integrated_report[field] += (current_quarter_report[field] or 0) - (previous_quarter_report[field] or 0)
        return integrated_report

    def normalize_report_date(self, statement):
        if 'report_date' not in statement and 'date' in statement:
            statement['report_date'] = statement['date']
        return statement

    def get_fields(self, table):
        df = self.config_service.get_table_config(table)
        fields = df['Field'].tolist()
        allowed = frozenset(financial_fields(table))
        fields = list(dict.fromkeys(f for f in fields if f in allowed))
        return fields
