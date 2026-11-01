# -*- coding: utf-8 -*-
import logging
import math

import pandas as pd

from saa_collector.services.abstract.statement_service import StatementService
from saa_collector.services.common.statement_maintain_service import StatementMaintainService
from saa_collector.services.common.progress import ProgressLogger
from saa_collector.services.common.statement_ingestion import (
    save_version_bundle, version_ingestion_enabled,
)
from saa_collector.services.common.statement_source_adapter import (
    TUSHARE_RESOURCES, TUSHARE_REPORT_TYPES, tushare_snapshots, CompleteStatementHistory,
)
from .basic_stock_service import BasicStockService


class StatementServiceImpl(StatementService, BasicStockService):
    RAW_STATEMENT_TABLES = {
        'saa_raw_balance_sheet',
        'saa_raw_income_statement',
        'saa_raw_cash_flow_statement',
        'saa_raw_main_business',
    }
    DISCLOSURE_FIELD_RESOURCES = {'balancesheet', 'income', 'cashflow'}

    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()
        self.maintain_service = StatementMaintainService()

    def produce(self, symbols, start_date=None, on_symbol_success=None,
                on_symbol_failure=None, after_symbol=None,
                progress_total_symbols=None, progress_completed_symbols=0,
                on_symbol_issue=None):
        symbols = self.build_symbols(symbols)
        failed_symbols = []
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
            except Exception as exc:
                self._logger.exception('Failed to produce statement for %s', symbol)
                progress.failed('Failed producing statement', symbol)
                failed_symbols.append(symbol)
                if on_symbol_issue:
                    issue = getattr(exc, 'issue', None) or {
                        'code': 'STATEMENT_COLLECTION_FAILED', 'provider': 'tushare',
                        'symbol': symbol, 'action': 'RETAIN_COMMITTED_DATA'}
                    on_symbol_issue(issue)
                if on_symbol_failure:
                    on_symbol_failure(symbol)
            else:
                if on_symbol_success:
                    on_symbol_success(symbol)
            finally:
                if after_symbol:
                    after_symbol(symbol)
        if (failed_symbols and not on_symbol_failure
                and version_ingestion_enabled(self.config)):
            raise RuntimeError('Financial statement production failed for: '
                               + ','.join(failed_symbols))

    def process(self, symbols, start_date=None):
        self.maintain_service.process(self.build_symbols(symbols))

    def collect(self, symbols, start_date=None):
        symbols = self.build_symbols(symbols)
        failed_symbols = []
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
            except Exception:
                self._logger.exception('Failed to collect statement for %s', symbol)
                progress.failed('Failed collecting statement', symbol)
                failed_symbols.append(symbol)
        if failed_symbols and version_ingestion_enabled(self.config):
            raise RuntimeError('Financial statement collection failed for: '
                               + ','.join(failed_symbols))

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

    def build_fields(self, table, sub_resource=None):
        table_config_df = self.config_service.get_table_config(table)
        field_series = table_config_df['TushareField']
        fields = field_series[field_series.notna()].tolist()
        fields.append('update_flag')
        if sub_resource in self.DISCLOSURE_FIELD_RESOURCES:
            fields.extend(['ann_date', 'f_ann_date'])
            if version_ingestion_enabled(self.config):
                fields.append('report_type')
        fields = [field.strip() for field in fields]
        fields = list(dict.fromkeys(fields))
        return ','.join(fields)

    def transform_records(self, raw_records, table):
        if table in TUSHARE_RESOURCES and version_ingestion_enabled(self.config):
            return tushare_snapshots(
                table, raw_records, self.config_service.get_table_config(table),
                latest_query_complete=isinstance(raw_records, CompleteStatementHistory))
        if table not in self.RAW_STATEMENT_TABLES:
            return super().transform_records(raw_records, table)

        table_config_df = self.config_service.get_table_config(table)
        records = []
        for raw_record in raw_records:
            record = self.transform_record(raw_record, table_config_df)
            if not record['date']:
                continue
            record.update({
                'symbol': self.convert_code(record['symbol']),
                'date': self.convert_date(record['date']),
            })
            records.append(self.normalize_statement_record(record, raw_record))
        return records

    def normalize_statement_record(self, record, raw_record):
        report_date = record.pop('date', None)
        record['report_date'] = report_date

        disclosure_date = raw_record.get('f_ann_date') or raw_record.get('ann_date')
        if disclosure_date and not (isinstance(disclosure_date, float) and math.isnan(disclosure_date)):
            record['disclosure_date'] = self.convert_date(disclosure_date)
        return record

    def query_record(self, sub_resource, symbol, **kwargs):
        if (sub_resource in self.DISCLOSURE_FIELD_RESOURCES
                and version_ingestion_enabled(self.config)):
            records = []
            requested = kwargs.pop('report_type', None)
            if requested is not None and requested not in TUSHARE_REPORT_TYPES:
                raise ValueError('Unsupported financial report type')
            if {'offset', 'limit'} & kwargs.keys():
                raise ValueError('Financial version pagination is managed internally')
            for report_type in (requested,) if requested else TUSHARE_REPORT_TYPES:
                seen_pages = set()
                for offset in range(0, 100000, 100):
                    frame = self.pro.query(sub_resource, ts_code=self.to_code(symbol),
                                           report_type=report_type, limit=100,
                                           offset=offset, **kwargs)
                    if frame is None or frame.columns.duplicated().any() or len(frame) > 100:
                        raise ValueError('Invalid financial source response')
                    rows = frame.to_dict('records')
                    if any(row.get('ts_code') != self.to_code(symbol)
                           or str(row.get('report_type')) != report_type for row in rows):
                        raise ValueError('Financial source response scope mismatch')
                    fingerprint = tuple(sorted(pd.util.hash_pandas_object(frame, index=False).tolist()))
                    if rows and fingerprint in seen_pages:
                        raise ValueError('Financial source pagination repeated a page')
                    seen_pages.add(fingerprint)
                    records.extend(rows)
                    self._logger.info('Financial history page: symbol=%s resource=%s type=%s offset=%d rows=%d',
                                      symbol, sub_resource, report_type, offset, len(rows))
                    if len(rows) < 100:
                        break
                else:
                    raise ValueError('Financial source pagination exceeded safety limit')
            if not records:
                raise ValueError('No financial versions returned for ' + symbol)
            # An announcement-date slice may omit an older genuine LATEST for
            # a period whose revision is returned. It cannot prove absence.
            complete = (requested is None and not kwargs.get('start_date')
                        and not kwargs.get('end_date'))
            return CompleteStatementHistory(records) if complete else records
        df = self.pro.query(sub_resource, ts_code=self.to_code(symbol), **kwargs)
        df = df.loc[:, ~df.columns.duplicated()].copy()
        if {'ts_code', 'end_date', 'update_flag'}.issubset(df.columns):
            df.sort_values(['ts_code', 'end_date', 'update_flag'], inplace=True)
            df.drop_duplicates(['ts_code', 'end_date'], keep='last', inplace=True)
        raw_records = df.to_dict('records')
        return raw_records

    def iter_symbol_records(self, sub_resource, symbols, **kwargs):
        if (sub_resource in self.DISCLOSURE_FIELD_RESOURCES
                and version_ingestion_enabled(self.config)):
            if isinstance(symbols, str):
                symbols = [symbols]
            for symbol in sorted(symbols):
                yield symbol, self.query_record(sub_resource, symbol, **kwargs)
            return
        yield from super().iter_symbol_records(sub_resource, symbols, **kwargs)

    def save_statements(self, records, table):
        if table in TUSHARE_RESOURCES and version_ingestion_enabled(self.config):
            return save_version_bundle(self.db_config, {table: records})
        primary_keys = ['symbol', 'report_date']
        if table == 'saa_raw_main_business':
            primary_keys.extend(['item_name', 'category'])
        self.save_records(records, table, primary_keys)

    def collect_statement_resource(
            self, sub_resource, table, symbols, start_date=None,
            progress_enabled=True):
        symbols = self.build_symbols(symbols)
        progress = self.build_progress(
            symbols, self.get_statement_resource_profile(sub_resource),
            start_date, progress_enabled
        )
        fields = self.build_fields(table, sub_resource=sub_resource)
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
        self.maintain_service.process(symbol)
        self._logger.info('End up processing statement for %s', symbol)

    def _collect_one(self, symbol, start_date=None):
        self._logger.info('Start to collect statement for %s', symbol)
        if version_ingestion_enabled(self.config):
            bundle = {}
            for table, resource in TUSHARE_RESOURCES.items():
                raw = self.query_record(resource, symbol,
                    fields=self.build_fields(table, resource),
                    start_date=self.build_date_param(start_date))
                bundle[table] = self.transform_records(raw, table)
            save_version_bundle(self.db_config, bundle)
            self.collect_dividend(symbol, start_date, progress_enabled=False)
            return
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
