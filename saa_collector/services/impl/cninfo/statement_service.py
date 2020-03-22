# -*- coding: utf-8 -*-

from saa_collector.services.abstract.statement_service import StatementService
from saa_collector.services.common.statement_maintain_service import StatementMaintainService
from .basic_stock_service import BasicStockService


class StatementServiceImpl(StatementService, BasicStockService):
    def __init__(self):
        super().__init__()
        self.maintain_service = StatementMaintainService()

    def produce(self, symbols, start_date=None):
        self.collect(symbols)
        self.process(symbols)

    def process(self, symbols, start_date=None):
        self.maintain_service.refresh_financial_report_cache(symbols)
        self.maintain_service.refresh_ttm_report_cache(symbols)

    def collect(self, symbols, start_date=None):
        symbols = self.build_symbols(symbols)
        start_date = self.build_start_date(start_date)
        self.collect_balance_sheet(symbols, start_date)
        self.collect_income(symbols, start_date)
        self.collect_cash_flow(symbols, start_date)
        self.collect_dividend(symbols, start_date)

    def collect_balance_sheet(self, symbols, start_date=None):
        table = 'saa_raw_balance_sheet'
        raw_records = self.query_records(symbols, 'p_stock2300', type='071001')
        records = self.transform_records(raw_records, table)
        records = self.filter_records(records, start_date)
        self.save_statements(records, table)

    def collect_income(self, symbols, start_date=None):
        table = 'saa_raw_income_statement'
        raw_records = self.query_records(symbols, 'p_stock2301', type='071001')
        records = self.transform_records(raw_records, table)
        records = self.filter_records(records, start_date)
        self.save_statements(records, table)

    def collect_cash_flow(self, symbols, start_date=None):
        table = 'saa_raw_cash_flow_statement'
        raw_records = self.query_records(symbols, 'p_stock2302', type='071001')
        records = self.transform_records(raw_records, table)
        records = self.filter_records(records, start_date)
        self.save_statements(records, table)

    def collect_dividend(self, symbols, start_date=None):
        sub_resource = 'p_stock2201'
        table = 'saa_dividends'
        table_config_df = self.config_service.get_table_config(table)
        raw_records = self.query_records(symbols, sub_resource)
        records = []
        for raw_record in raw_records:
            record = self.transform_record(raw_record, table_config_df)
            if not record['date'] or not record['dividend']:
                continue
            records.append(record)
        records = self.filter_records(records, start_date)
        self.save_statements(records, table)

    def save_statements(self, records, statement):
        self.save_records(records, statement, ['symbol', 'date'])
