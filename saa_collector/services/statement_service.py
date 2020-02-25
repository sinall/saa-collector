# -*- coding: utf-8 -*-
import copy
import datetime
import itertools

import mysql.connector

from .basic_stock_service import BasicStockService
from ..utils.db import DB


class StatementService(BasicStockService):
    def __init__(self):
        super().__init__()

    def produce(self, symbols):
        self.collect(symbols)
        self.process(symbols)

    def process(self, symbols):
        self.refresh_financial_report_cache(symbols)
        self.refresh_ttm_report_cache(symbols)

    def collect(self, symbols):
        symbols = self.build_symbols(symbols)
        self.collect_balance_sheet(symbols)
        self.collect_income(symbols)
        self.collect_cash_flow(symbols)
        self.collect_dividend(symbols)

    def collect_balance_sheet(self, symbols):
        self.collect_statement(symbols, 'p_stock2300', 'saa_raw_balance_sheet', type='071001')

    def collect_income(self, symbols):
        self.collect_statement(symbols, 'p_stock2301', 'saa_raw_income_statement', type='071001')

    def collect_cash_flow(self, symbols):
        self.collect_statement(symbols, 'p_stock2302', 'saa_raw_cash_flow_statement', type='071001')

    def collect_dividend(self, symbols):
        sub_resource = 'p_stock2201'
        statement = 'saa_dividends'
        table_config_df = self.xls_file.parse(statement)
        raw_records = self.query_records(symbols, sub_resource)
        records = []
        for raw_record in raw_records:
            record = self.transform_record(raw_record, table_config_df)
            if not record['date'] or not record['dividend']:
                continue
            records.append(record)
        cnx = mysql.connector.connect(**self.db_config)
        DB().to_sql(records, cnx, statement, ['symbol', 'date'])

    def refresh_financial_report_cache(self, symbols):
        if symbols:
            if isinstance(symbols, str):
                args = (symbols,)
            else:
                args = (','.join(symbols),)
        else:
            args = ()
        cnx = mysql.connector.connect(**self.db_config)
        cursor = cnx.cursor()
        cursor.callproc('saa_refresh_integrated_reports_cache', args)
        cnx.commit()

    def refresh_ttm_report_cache(self, symbols):
        income_fields = self.get_fields("saa_raw_income_statement")
        cash_flow_fields = self.get_fields("saa_raw_cash_flow_statement")
        non_balance_sheet_fields = income_fields + cash_flow_fields

        if symbols:
            sql = "SELECT * FROM saa_integrated_reports_interface " \
                  "WHERE symbol IN (%s) AND date >= DATE_SUB(CURDATE(), INTERVAL 4 YEAR)"
            if isinstance(symbols, str):
                param_count = 1
                params = (symbols,)
            else:
                param_count = len(symbols)
                params = tuple(symbols)
            sql = sql % ','.join(['%s'] * param_count)
        else:
            sql = "SELECT * FROM saa_integrated_reports_interface " \
                  "WHERE date >= DATE_SUB(CURDATE(), INTERVAL 4 YEAR)"
            params = ()
        cnx = mysql.connector.connect(**self.db_config)
        cursor = cnx.cursor(dictionary=True)
        cursor.execute(sql, params)
        all_statements = cursor.fetchall()
        symbol_to_statements = itertools.groupby(all_statements, lambda s: s['symbol'])
        integrated_reports = []
        for symbol, statements in symbol_to_statements:
            integrated_report = self.gen_ttm_report(statements, non_balance_sheet_fields)
            if not integrated_report:
                continue
            integrated_reports.append(integrated_report)

        DB().to_sql(integrated_reports, cnx, "saa_ttm_reports_interface", "symbol")

    def gen_ttm_report(self, statements, non_balance_sheet_fields):
        statements = sorted(statements, key=lambda i: i['date'], reverse=True)
        latest_integrate_report = statements[0]
        if latest_integrate_report['date'].month is 12:
            return latest_integrate_report
        date_to_integrated_report_list = {r['date']: r for r in statements}
        current_quarter_report = latest_integrate_report
        current_report_date = latest_integrate_report['date']
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

    def get_fields(self, table):
        df = self.xls_file.parse(table)
        fields = df['Field'].tolist()
        fields = [f for f in fields if f not in ('symbol', 'date')]
        return fields
