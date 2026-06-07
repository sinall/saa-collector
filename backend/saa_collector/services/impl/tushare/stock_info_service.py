# -*- coding: utf-8 -*-
import logging
import time

import mysql.connector

from saa_collector.services.abstract.stock_info_service import StockInfoService
from saa_collector.services.common.progress import ProgressLogger
from saa_collector.services.common.security_master_service import SecurityMasterRefreshService
from saa_collector.utils.db import DB
from .basic_stock_service import BasicStockService

DEFAULT_SAVE_INTERVAL_SECONDS = 600  # 10 minutes

EXCHANGE_DICT = {
    'SZSE': 'SZ',
    'SSE': 'SH',
}

BOARD_DICT = {
    '': 'MAIN_BOARD',
    '主板': 'MAIN_BOARD',
    '中小板': 'SMALL_AND_MEDIUM_ENTERPRISES',
    '创业板': 'CHINEXT',
    '科创板': 'STAR',
}


class StockInfoServiceImpl(StockInfoService, BasicStockService):
    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()

    def collect(self, symbols, progress_enabled=True):
        start_time = time.time()
        symbols = self.build_symbols(symbols)
        total = len(symbols)
        self._logger.info('Start collecting stock info for %d symbols', total)
        progress = None
        if progress_enabled:
            progress = ProgressLogger.for_symbols(
                self._logger,
                symbols,
                profile='stock_info',
            )

        save_interval = self._get_save_interval()
        table_config_df = self.config_service.get_table_config('saa_stocks')

        cnx = self._create_connection()
        accumulated_records = []
        last_save_time = time.time()

        try:
            for symbol in symbols:
                try:
                    record = self._get_stock_info_for_symbol(symbol, table_config_df)
                    if record:
                        accumulated_records.append(record)
                    if progress:
                        progress.finished('Finished collecting stock info', symbol)
                except Exception as e:
                    self._logger.error(
                        'Failed to process symbol %s: %s', symbol, e
                    )
                    if progress:
                        progress.failed('Failed collecting stock info', symbol)

                elapsed = time.time() - last_save_time
                if elapsed >= save_interval and accumulated_records:
                    cnx = self._save_batch_with_retry(accumulated_records, cnx)
                    self._logger.info(
                        'Checkpoint: saved %d records after %ds (progress %d/%d)',
                        len(accumulated_records), int(elapsed), idx, total
                    )
                    accumulated_records = []
                    last_save_time = time.time()

            if accumulated_records:
                cnx = self._save_batch_with_retry(accumulated_records, cnx)
                self._logger.info(
                    'Final batch: saved %d records', len(accumulated_records)
                )

            SecurityMasterRefreshService().refresh_from_stocks(cnx)
        finally:
            try:
                cnx.close()
            except Exception:
                pass

        self._logger.info(
            'Completed stock info collection: %d symbols in %ds',
            total, int(time.time() - start_time)
        )

    def build_symbols(self, symbols):
        if isinstance(symbols, str):
            symbols = [symbols]
        if not symbols:
            df = self.pro.query('stock_basic', fields='ts_code,symbol', list_status='L')
            symbols = df['symbol'].tolist()
        return symbols

    def get_stock_info_list(self, scode_list):
        table_config_df = self.config_service.get_table_config('saa_stocks')
        records = []
        for symbol in scode_list:
            try:
                record = self._get_stock_info_for_symbol(symbol, table_config_df)
                if record:
                    records.append(record)
            except Exception as e:
                self._logger.error(
                    'Failed to get stock info for symbol %s: %s', symbol, e
                )
        return records

    def _get_stock_info_for_symbol(self, symbol, table_config_df):
        raw_records = self.query_record(
            'stock_basic', symbol,
            fields='ts_code,symbol,name,area,industry,list_date,market,exchange'
        )
        if not raw_records:
            self._logger.warning('No stock_basic data for symbol %s', symbol)
            return None

        raw_record = raw_records[0]
        list_date = raw_record['list_date']
        stock_info = {
            'symbol': raw_record['symbol'],
            'name': raw_record['name'],
            'exchange': EXCHANGE_DICT[raw_record['exchange']],
            'board': BOARD_DICT[raw_record['market']],
            'listing_date': "{}-{}-{}".format(list_date[:4], list_date[4:6], list_date[6:]),
        }

        try:
            company_records = self.query_record(
                'stock_company', symbol,
                fields='ts_code,exchange,introduction,chairman,secretary,reg_capital,website'
            )
            if company_records:
                company_info = self.transform_record(company_records[0], table_config_df)
                company_info.update({
                    'symbol': self.convert_code(company_info['symbol']),
                })
                stock_info.update(company_info)
            else:
                self._logger.warning(
                    'No company data for symbol %s, skipping company info', symbol
                )
        except Exception as e:
            self._logger.warning(
                'Failed to get company data for symbol %s: %s', symbol, e
            )

        return stock_info

    def _get_save_interval(self):
        tushare_config = self.config.get('saa_collector', {}).get('tushare_api', {})
        return tushare_config.get('save_interval', DEFAULT_SAVE_INTERVAL_SECONDS)

    def _create_connection(self):
        return mysql.connector.connect(**self.db_config)

    def _ensure_connection(self, cnx):
        """Check if connection is alive, reconnect if needed."""
        try:
            cnx.ping(reconnect=True, attempts=3, delay=2)
            return cnx
        except Exception:
            self._logger.warning('MySQL connection lost, reconnecting...')
            try:
                cnx.close()
            except Exception:
                pass
            return self._create_connection()

    def _save_batch_with_retry(self, records, cnx, max_retries=3):
        """Save batch with retry on connection failure."""
        for attempt in range(max_retries):
            try:
                cnx = self._ensure_connection(cnx)
                DB().to_sql(records, cnx, 'saa_stocks', 'symbol')
                return cnx
            except (mysql.connector.errors.OperationalError,
                    mysql.connector.errors.InterfaceError) as e:
                self._logger.warning(
                    'Save batch failed (attempt %d/%d): %s',
                    attempt + 1, max_retries, e
                )
                if attempt < max_retries - 1:
                    try:
                        cnx.close()
                    except Exception:
                        pass
                    cnx = self._create_connection()
                else:
                    raise
        return cnx

    def _save_batch(self, records, cnx):
        DB().to_sql(records, cnx, 'saa_stocks', 'symbol')
