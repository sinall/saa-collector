# -*- coding: utf-8 -*-
import math

from saa_collector.services.abstract.capital_service import CapitalService
from saa_collector.services.common.progress import ProgressLogger
from .basic_stock_service import BasicStockService


class CapitalServiceImpl(CapitalService, BasicStockService):
    def __init__(self):
        super().__init__()

    def collect(self, symbols, start_date=None, progress_enabled=True):
        sub_resource = 'dividend'
        table = 'saa_capitals'
        symbols = self.build_symbols(symbols)
        progress = None
        if progress_enabled:
            progress = ProgressLogger.for_symbols(
                self._logger,
                symbols,
                profile='capital',
                start_date=start_date,
            )
        batch_symbols = self.get_save_batch_symbols()
        batch_records = []
        pending_symbols = []
        processed_symbols = 0
        for symbol, raw_records in self.iter_symbol_records(
            sub_resource, symbols, fields='ts_code,stk_bo_rate,stk_co_rate,base_share,ex_date'
        ):
            records = []
            for raw_record in raw_records:
                record = self.build_capital_record(raw_record)
                if not record:
                    self._logger.debug(
                        'Skipped invalid capital raw record for symbol %s: %s',
                        symbol, raw_record
                    )
                    continue
                records.append(record)
            records = self.filter_records(records, start_date)
            batch_records.extend(records)
            processed_symbols += 1
            pending_symbols.append(symbol)
            if batch_records and processed_symbols % batch_symbols == 0:
                self.save_records(batch_records, table, ['symbol', 'date'])
                self.finish_pending_progress(progress, pending_symbols)
                batch_records = []
                pending_symbols = []
        if batch_records:
            self.save_records(batch_records, table, ['symbol', 'date'])
        self.finish_pending_progress(progress, pending_symbols)

    def finish_pending_progress(self, progress, pending_symbols):
        if not progress:
            return
        for pending_symbol in pending_symbols:
            progress.finished('Finished collecting capital', pending_symbol)

    def build_capital_record(self, raw_record):
        ts_code = raw_record.get('ts_code')
        ex_date = raw_record.get('ex_date')
        base_share = self.clean_number(raw_record.get('base_share'))
        if not ts_code or not ex_date or base_share is None:
            return None

        stk_bo_rate = self.clean_number(raw_record.get('stk_bo_rate'), default=0)
        stk_co_rate = self.clean_number(raw_record.get('stk_co_rate'), default=0)
        capital = base_share * 10000 * (1 + stk_bo_rate + stk_co_rate)
        if not capital:
            return None
        return {
            'symbol': self.convert_code(ts_code),
            'date': self.convert_date(ex_date),
            'capital': capital,
        }

    def clean_number(self, value, default=None):
        if value is None:
            return default
        try:
            if math.isnan(value):
                return default
        except TypeError:
            pass
        return value
