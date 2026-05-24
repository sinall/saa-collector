# -*- coding: utf-8 -*-
import logging
import math

from saa_collector.services.abstract.statement_service import StatementService
from saa_collector.services.common.statement_maintain_service import StatementMaintainService
from saa_collector.services.common.progress import ProgressLogger
from .basic_stock_service import BasicStockService


class StatementServiceImpl(StatementService, BasicStockService):
    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()
        self.maintain_service = StatementMaintainService()

    def produce(self, symbols, start_date=None, on_symbol_success=None,
                on_symbol_failure=None, after_symbol=None,
                progress_total_symbols=None, progress_completed_symbols=0):
        symbols = self.build_symbols(symbols)
        progress = ProgressLogger.for_symbols(
            self._logger,
            symbols,
            profile='financial_statements',
            start_date=start_date,
            display_completed_items=progress_completed_symbols,
            display_total_items=progress_total_symbols,
        )
        for symbol in symbols:
            try:
                self._produce_one(symbol, start_date)
                progress.finished('Finished producing statement', symbol)
            except:
                self._logger.exception('Failed to produce statement for %s', symbol)
                progress.failed('Failed producing statement', symbol)
                if on_symbol_failure:
                    on_symbol_failure(symbol)
            else:
                if on_symbol_success:
                    on_symbol_success(symbol)
            finally:
                if after_symbol:
                    after_symbol(symbol)

    def process(self, symbols, start_date=None):
        self.maintain_service.refresh_financial_report_cache(symbols)
        self.maintain_service.refresh_ttm_report_cache(symbols)

    def collect(self, symbols, start_date=None):
        symbols = self.build_symbols(symbols)
        progress = ProgressLogger.for_symbols(
            self._logger,
            symbols,
            profile='financial_statements',
            start_date=start_date,
        )
        for symbol in symbols:
            try:
                self._collect_one(symbol, start_date)
                progress.finished('Finished collecting statement', symbol)
            except:
                self._logger.exception('Failed to collect statement for %s', symbol)
                progress.failed('Failed collecting statement', symbol)

    def collect_balance_sheet(self, symbols, start_date=None, progress_enabled=True):
        table = 'saa_raw_balance_sheet'
        self.collect_statement_resource(
            'balancesheet', table, symbols, start_date=start_date,
            progress_enabled=progress_enabled
        )

    def collect_income(self, symbols, start_date=None, progress_enabled=True):
        table = 'saa_raw_income_statement'
        self.collect_statement_resource(
            'income', table, symbols, start_date=start_date,
            progress_enabled=progress_enabled
        )

    def collect_cash_flow(self, symbols, start_date=None, progress_enabled=True):
        table = 'saa_raw_cash_flow_statement'
        self.collect_statement_resource(
            'cashflow', table, symbols, start_date=start_date,
            progress_enabled=progress_enabled
        )

    def collect_dividend(self, symbols, start_date=None, progress_enabled=True):
        sub_resource = 'dividend'
        table = 'saa_dividends'
        symbols = self.build_symbols(symbols)
        progress = self.build_progress(
            symbols, 'dividend', start_date, progress_enabled
        )
        batch_symbols = self.get_save_batch_symbols()
        batch_records = []
        pending_symbols = []
        processed_symbols = 0
        for symbol, raw_records in self.iter_symbol_records(
            sub_resource, symbols,
            fields='ts_code,cash_div_tax,base_share,ex_date', start_date=self.build_date_param(start_date)
        ):
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
                batch_records.append(record)
            processed_symbols += 1
            pending_symbols.append(symbol)
            self._logger.info('Prepared %d %s records for symbol %s', len(records), table, symbol)
            if batch_records and processed_symbols % batch_symbols == 0:
                self.save_statements(batch_records, table)
                self._logger.info('Saved %d %s records', len(batch_records), table)
                self.finish_pending_progress(
                    progress, pending_symbols, 'Finished collecting dividend'
                )
                batch_records = []
                pending_symbols = []
        if batch_records:
            self.save_statements(batch_records, table)
            self._logger.info('Saved final %d %s records', len(batch_records), table)
        self.finish_pending_progress(
            progress, pending_symbols, 'Finished collecting dividend'
        )

    def collect_main_business(self, symbols, start_date=None, progress_enabled=True):
        table = 'saa_raw_main_business'
        symbols = self.build_symbols(symbols)
        progress = self.build_progress(
            symbols, 'main_business', start_date, progress_enabled
        )
        batch_symbols = self.get_save_batch_symbols()
        batch_records = []
        pending_symbols = []
        processed_symbols = 0
        for symbol in symbols:
            raw_records_by_product = self.query_main_business_by(symbol, 'P', start_date=start_date)
            raw_records_by_region = self.query_main_business_by(symbol, 'D', start_date=start_date)
            raw_records = raw_records_by_product + raw_records_by_region
            records = self.transform_records(raw_records, table)
            for record in records:
                category = record['category']
                record['category'] = {'P': 'PRODUCT', 'D': 'REGION'}[category]
                try:
                    record['gross_profit_margin'] = record['main_business_profit'] / record['main_business_income']
                except:
                    pass
            batch_records.extend(records)
            processed_symbols += 1
            pending_symbols.append(symbol)
            self._logger.info('Prepared %d %s records for symbol %s', len(records), table, symbol)
            if batch_records and processed_symbols % batch_symbols == 0:
                self.save_statements(batch_records, table)
                self._logger.info('Saved %d %s records', len(batch_records), table)
                self.finish_pending_progress(
                    progress, pending_symbols, 'Finished collecting main business'
                )
                batch_records = []
                pending_symbols = []
        if batch_records:
            self.save_statements(batch_records, table)
            self._logger.info('Saved final %d %s records', len(batch_records), table)
        self.finish_pending_progress(
            progress, pending_symbols, 'Finished collecting main business'
        )

    def query_main_business_by(self, symbols, type, start_date=None):
        table = 'saa_raw_main_business'
        fields = self.build_fields(table)
        fields = fields.replace('type,', '')
        raw_records = self.query_records(
            'fina_mainbz', symbols, fields=fields, type=type, start_date=self.build_date_param(start_date)
        )
        for raw_record in raw_records:
            raw_record['type'] = type
        return raw_records

    def build_fields(self, table):
        table_config_df = self.config_service.get_table_config(table)
        field_series = table_config_df['TushareField']
        fields = field_series[field_series.notna()].tolist()
        fields.append('update_flag')
        return ','.join(fields)

    def query_record(self, sub_resource, symbol, **kwargs):
        df = self.pro.query(sub_resource, ts_code=self.to_code(symbol), **kwargs)
        df = df.loc[:, ~df.columns.duplicated()].copy()
        if {'ts_code', 'end_date', 'update_flag'}.issubset(df.columns):
            df.sort_values(['ts_code', 'end_date', 'update_flag'], inplace=True)
            df.drop_duplicates(['ts_code', 'end_date'], keep='last', inplace=True)
        raw_records = df.to_dict('records')
        return raw_records

    def save_statements(self, records, table):
        self.save_records(records, table, ['symbol', 'date'])

    def collect_statement_resource(
            self, sub_resource, table, symbols, start_date=None,
            progress_enabled=True):
        symbols = self.build_symbols(symbols)
        progress = self.build_progress(
            symbols, self.get_statement_resource_profile(sub_resource),
            start_date, progress_enabled
        )
        fields = self.build_fields(table)
        start_date_param = self.build_date_param(start_date)
        batch_symbols = self.get_save_batch_symbols()
        batch_records = []
        pending_symbols = []
        processed_symbols = 0
        for symbol, raw_records in self.iter_symbol_records(
            sub_resource, symbols, fields=fields, start_date=start_date_param
        ):
            records = self.transform_records(raw_records, table)
            batch_records.extend(records)
            processed_symbols += 1
            pending_symbols.append(symbol)
            self._logger.info('Prepared %d %s records for symbol %s', len(records), table, symbol)
            if batch_records and processed_symbols % batch_symbols == 0:
                self.save_statements(batch_records, table)
                self._logger.info('Saved %d %s records', len(batch_records), table)
                self.finish_pending_progress(
                    progress, pending_symbols,
                    'Finished collecting {}'.format(sub_resource)
                )
                batch_records = []
                pending_symbols = []
        if batch_records:
            self.save_statements(batch_records, table)
            self._logger.info('Saved final %d %s records', len(batch_records), table)
        self.finish_pending_progress(
            progress, pending_symbols,
            'Finished collecting {}'.format(sub_resource)
        )

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
        self.collect_balance_sheet(symbol, start_date, progress_enabled=False)
        self.collect_income(symbol, start_date, progress_enabled=False)
        self.collect_cash_flow(symbol, start_date, progress_enabled=False)
        self.collect_dividend(symbol, start_date, progress_enabled=False)
        self._logger.info('End up collecting statement for %s', symbol)

    def build_progress(self, symbols, profile, start_date, progress_enabled):
        if not progress_enabled:
            return None
        return ProgressLogger.for_symbols(
            self._logger,
            symbols,
            profile=profile,
            start_date=start_date,
        )

    def finish_pending_progress(self, progress, pending_symbols, message):
        if not progress:
            return
        for pending_symbol in pending_symbols:
            progress.finished(message, pending_symbol)

    def get_statement_resource_profile(self, sub_resource):
        return {
            'balancesheet': 'balance_sheet',
            'income': 'income',
            'cashflow': 'cash_flow',
        }.get(sub_resource, 'default')
