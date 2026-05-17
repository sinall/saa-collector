# -*- coding: utf-8 -*-

from saa_collector.services.abstract.capital_service import CapitalService
from saa_collector.services.common.progress import ProgressLogger
from .basic_stock_service import BasicStockService


class CapitalServiceImpl(CapitalService, BasicStockService):
    def __init__(self):
        super().__init__()

    def collect(self, symbols, start_date=None):
        sub_resource = 'dividend'
        table = 'saa_capitals'
        symbols = self.build_symbols(symbols)
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
                ts_code = raw_record['ts_code']
                base_share = raw_record['base_share'] * 10000
                multiplier = (1 + (raw_record['stk_bo_rate'] or 0) + (raw_record['stk_co_rate'] or 0))
                record = {
                    'symbol': self.convert_code(ts_code),
                    'date': self.convert_date(raw_record['ex_date']),
                    'capital': base_share * multiplier,
                }
                if not record['date'] or not record['capital']:
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
        for pending_symbol in pending_symbols:
            progress.finished('Finished collecting capital', pending_symbol)
