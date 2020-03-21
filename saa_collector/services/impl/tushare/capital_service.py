# -*- coding: utf-8 -*-

from saa_collector.services.abstract.capital_service import CapitalService
from .basic_stock_service import BasicStockService


class CapitalServiceImpl(CapitalService, BasicStockService):
    def __init__(self):
        super().__init__()

    def collect(self, symbols, start_date=None):
        sub_resource = 'dividend'
        table = 'saa_capitals'
        symbols = self.build_symbols(symbols)
        raw_records = self.query_records(
            sub_resource, symbols, fields='ts_code,stk_bo_rate,stk_co_rate,base_share,ex_date'
        )
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
        self.save_records(records, table, ['symbol', 'date'])
