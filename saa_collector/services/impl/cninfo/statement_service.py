# -*- coding: utf-8 -*-

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
