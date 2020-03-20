# -*- coding: utf-8 -*-

from saa_collector.services.abstract.capital_service import CapitalService
from .basic_stock_service import BasicStockService


class CapitalServiceImpl(CapitalService, BasicStockService):
    def __init__(self):
        super().__init__()

    def collect(self, symbols, start_date=None):
        symbols = self.build_symbols(symbols)
        table = 'saa_capitals'
        raw_records = self.query_records(symbols, 'p_stock2215')
        records = self.transform_records(raw_records, table)
        records = self.filter_records(records, start_date)
        self.save_records(records, table)
