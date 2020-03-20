# -*- coding: utf-8 -*-
import math

from saa_collector.services.abstract.statement_service import StatementService
from saa_collector.services.common.statement_maintain_service import StatementMaintainService
from .basic_stock_service import BasicStockService


class StatementServiceImpl(StatementService, BasicStockService):
    def __init__(self):
        super().__init__()
        self.maintain_service = StatementMaintainService()

    def produce(self, symbols, start_date=None):
        self.collect(symbols, start_date)
        self.process(symbols)

    def process(self, symbols, start_date=None):
        self.maintain_service.refresh_financial_report_cache(symbols)
        self.maintain_service.refresh_ttm_report_cache(symbols)

    def collect(self, symbols, start_date=None):
        symbols = self.build_symbols(symbols)
        start_date = self.build_date_param(start_date)
        self.collect_balance_sheet(symbols, start_date)
        self.collect_income(symbols, start_date)
        self.collect_cash_flow(symbols, start_date)
        self.collect_dividend(symbols, start_date)

    def collect_balance_sheet(self, symbols, start_date=None):
        table = 'saa_raw_balance_sheet'
        raw_records = self.query_records('balancesheet', symbols, type='1', start_date=start_date)
        records = self.transform_records(raw_records, table)
        self.save_statements(records, table)

    def collect_income(self, symbols, start_date=None):
        table = 'saa_raw_income_statement'
        raw_records = self.query_records('income', symbols, type='1', start_date=start_date)
        records = self.transform_records(raw_records, table)
        self.save_statements(records, table)

    def collect_cash_flow(self, symbols, start_date=None):
        table = 'saa_raw_cash_flow_statement'
        raw_records = self.query_records('cashflow', symbols, type='1', start_date=start_date)
        records = self.transform_records(raw_records, table)
        self.save_statements(records, table)

    def collect_dividend(self, symbols, start_date=None):
        sub_resource = 'dividend'
        table = 'saa_dividends'
        raw_records = self.query_records(
            sub_resource, symbols, fields='ts_code,cash_div_tax,base_share,ex_date', start_date=start_date
        )
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
        self.save_statements(records, table)

    def save_statements(self, records, table):
        self.save_records(records, table, ['symbol', 'date'])
