# -*- coding: utf-8 -*-
import math

import mysql.connector

from saa_collector.services.abstract.statement_service import StatementService
from saa_collector.services.common.statement_maintain_service import StatementMaintainService
from saa_collector.utils.db import DB
from .basic_stock_service import BasicStockService


class StatementServiceImpl(StatementService, BasicStockService):
    def __init__(self):
        super().__init__()
        self.maintain_service = StatementMaintainService()

    def produce(self, symbols):
        self.collect(symbols)
        self.process(symbols)

    def process(self, symbols, start_date=None):
        self.maintain_service.refresh_financial_report_cache(symbols)
        self.maintain_service.refresh_ttm_report_cache(symbols)

    def collect(self, symbols):
        symbols = self.build_symbols(symbols)
        self.collect_balance_sheet(symbols)
        self.collect_income(symbols)
        self.collect_cash_flow(symbols)
        self.collect_dividend(symbols)

    def collect_balance_sheet(self, symbols):
        self.collect_statement(symbols, 'balancesheet', 'saa_raw_balance_sheet', type='1')

    def collect_income(self, symbols):
        self.collect_statement(symbols, 'income', 'saa_raw_income_statement', type='1')

    def collect_cash_flow(self, symbols):
        self.collect_statement(symbols, 'cashflow', 'saa_raw_cash_flow_statement', type='1')

    def collect_dividend(self, symbols):
        sub_resource = 'dividend'
        statement = 'saa_dividends'
        raw_records = self.query_records(symbols, sub_resource, fields='ts_code,cash_div_tax,base_share,ex_date')
        records = []
        for raw_record in raw_records:
            ts_code = raw_record['ts_code']
            dividend = (raw_record['cash_div_tax'] or 0) * ((raw_record['base_share'] or 0) * 10000)
            record = {
                'symbol': self.convert_code(ts_code),
                'date': self.convert_date(raw_record['ex_date']),
                'dps': raw_record['cash_div_tax'],
                'dividend': dividend if math.isnan(dividend) else round(dividend),
            }
            if not record['date'] or not record['dividend']:
                continue
            records.append(record)
        cnx = mysql.connector.connect(**self.db_config)
        DB().to_sql(records, cnx, statement, ['symbol', 'date'])
