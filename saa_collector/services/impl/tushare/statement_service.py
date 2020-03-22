# -*- coding: utf-8 -*-
import logging
import math

from saa_collector.services.abstract.statement_service import StatementService
from saa_collector.services.common.statement_maintain_service import StatementMaintainService
from .basic_stock_service import BasicStockService


class StatementServiceImpl(StatementService, BasicStockService):
    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()
        self.maintain_service = StatementMaintainService()

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
        table = 'saa_raw_balance_sheet'
        raw_records = self.query_records(
            'balancesheet', symbols, fields=self.build_fields(table), start_date=self.build_date_param(start_date)
        )
        records = self.transform_records(raw_records, table)
        self.save_statements(records, table)

    def collect_income(self, symbols, start_date=None):
        table = 'saa_raw_income_statement'
        raw_records = self.query_records(
            'income', symbols, fields=self.build_fields(table), start_date=self.build_date_param(start_date)
        )
        records = self.transform_records(raw_records, table)
        self.save_statements(records, table)

    def collect_cash_flow(self, symbols, start_date=None):
        table = 'saa_raw_cash_flow_statement'
        raw_records = self.query_records(
            'cashflow', symbols, fields=self.build_fields(table), start_date=self.build_date_param(start_date)
        )
        records = self.transform_records(raw_records, table)
        self.save_statements(records, table)

    def collect_dividend(self, symbols, start_date=None):
        sub_resource = 'dividend'
        table = 'saa_dividends'
        raw_records = self.query_records(
            sub_resource, symbols,
            fields='ts_code,cash_div_tax,base_share,ex_date', start_date=self.build_date_param(start_date)
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

    def build_fields(self, table):
        table_config_df = self.config_service.get_table_config(table)
        field_series = table_config_df['TushareField']
        fields = field_series[field_series.notna()].tolist()
        fields.append('update_flag')
        return ','.join(fields)

    def query_record(self, sub_resource, symbol, **kwargs):
        df = self.pro.query(sub_resource, ts_code=self.to_code(symbol), **kwargs)
        if {'ts_code', 'end_date', 'update_flag'}.issubset(df.columns):
            df.sort_values(['ts_code', 'end_date', 'update_flag'], inplace=True)
            df.drop_duplicates(['ts_code', 'end_date'], keep='last', inplace=True)
        raw_records = df.to_dict('records')
        return raw_records

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
