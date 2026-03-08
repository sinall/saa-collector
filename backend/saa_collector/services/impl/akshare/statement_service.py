# -*- coding: utf-8 -*-
import logging

from saa_collector.services.abstract.statement_service import StatementService
from saa_collector.services.common.statement_maintain_service import StatementMaintainService
from .basic_stock_service import BasicStockService
import akshare as ak

from ...common.stock_utils import StockUtils


class StatementServiceImpl(StatementService, BasicStockService):
    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()
        self.maintain_service = StatementMaintainService()
        self.report_mapping = {
            'balance_sheet': '资产负债表',
            'income_statement': '利润表',
            'cash_flow_statement': '现金流量表'
        }

    def produce(self, symbols, start_date=None):
        symbols = self.build_symbols(symbols)
        for symbol in symbols:
            try:
                self._produce_one(symbol, start_date)
            except:
                self._logger.exception('Failed to produce statement for %s', symbol)

    def process(self, symbols, start_date=None):
        self.maintain_service.refresh_financial_report_cache(symbols)
        self.maintain_service.refresh_ttm_report_cache(symbols)

    def collect(self, symbols, start_date=None):
        symbols = self.build_symbols(symbols)
        for symbol in symbols:
            try:
                self._collect_one(symbol, start_date)
            except:
                self._logger.exception('Failed to collect statement for %s', symbol)

    def collect_balance_sheet(self, symbols, start_date=None):
        sub_resource = 'balance_sheet'
        table = self._get_table(sub_resource)
        df = self.query(sub_resource, symbols, self.channel, start_date)
        records = df.to_dict('records')
        self.save_statements(records, table)

    def collect_income(self, symbols, start_date=None):
        sub_resource = 'income_statement'
        table = self._get_table(sub_resource)
        df = self.query(sub_resource, symbols, self.channel, start_date)
        records = df.to_dict('records')
        self.save_statements(records, table)

    def collect_cash_flow(self, symbols, start_date=None):
        sub_resource = 'cash_flow_statement'
        table = self._get_table(sub_resource)
        df = self.query(sub_resource, symbols, self.channel, start_date)
        records = df.to_dict('records')
        self.save_statements(records, table)

    def collect_dividend(self, symbols, start_date=None):
        sub_resource = 'dividend'
        table = self._get_table(sub_resource)
        df = self.query(sub_resource, symbols, self.channel, start_date)
        records = df.to_dict('records')
        self.save_statements(records, table)

    def collect_main_business(self, symbols, start_date=None):
        sub_resource = 'main_business'
        table = self._get_table(sub_resource)
        df = self.query(sub_resource, symbols, self.channel, start_date)
        records = df.to_dict('records')
        self.save_statements(records, table)

    def build_fields(self, table):
        table_config_df = self.config_service.get_table_config(table)
        field_series = table_config_df['TushareField']
        fields = field_series[field_series.notna()].tolist()
        fields.append('update_flag')
        return ','.join(fields)

    def query_record(self, sub_resource, symbol, **kwargs):
        if sub_resource == "dividend":
            df = ak.stock_fhps_detail_em(symbol=self.to_code(symbol))
        elif sub_resource == "main_business":
            df = ak.stock_zygc_em(symbol=StockUtils.format(symbol, '{market}{code}'))
        else:
            df = ak.stock_financial_report_sina(stock=self.to_code(symbol), symbol=self._translate(sub_resource))
        df["证券代码"] = symbol
        raw_records = df.to_dict('records')
        return raw_records

    def query_one(self, sub_resource, symbol, **kwargs):
        if sub_resource == "dividend":
            df = ak.stock_fhps_detail_em(symbol=self.to_code(symbol))
        elif sub_resource == "main_business":
            df = ak.stock_zygc_em(symbol=StockUtils.format(symbol, '{market}{code}'))
        else:
            df = ak.stock_financial_report_sina(stock=self.to_code(symbol), symbol=self._translate(sub_resource))
        return df

    def save_statements(self, records, table):
        self.save_records(records, table, ['symbol', 'date'])

    def _produce_one(self, symbol, start_date=None):
        self._logger.info('Start to produce statement for %s', symbol)
        self._collect_one(symbol, start_date)
        self._process_one(symbol)
        self._logger.info('End up producing statement for %s', symbol)

    def _process_one(self, symbol, start_date=None):
        self._logger.info('Start to process statement for %s', symbol)
        self.maintain_service.refresh_financial_report_cache(symbol)
        self._logger.info('End up refresh-financial-report-cache for %s', symbol)
        self.maintain_service.refresh_ttm_report_cache(symbol)
        self._logger.info('End up refresh-ttm-report-cache for %s', symbol)
        self._logger.info('End up processing statement for %s', symbol)

    def _collect_one(self, symbol, start_date=None):
        self._logger.info('Start to collect statement for %s', symbol)
        self.collect_balance_sheet(symbol, start_date)
        self.collect_income(symbol, start_date)
        self.collect_cash_flow(symbol, start_date)
        self.collect_dividend(symbol, start_date)
        self._logger.info('End up collecting statement for %s', symbol)

    def _translate(self, statement_en):
        return self.report_mapping.get(statement_en.lower(), statement_en)
