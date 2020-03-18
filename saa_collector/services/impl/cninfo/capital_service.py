# -*- coding: utf-8 -*-

from saa_collector.services.abstract.capital_service import CapitalService
from .basic_stock_service import BasicStockService


class CapitalServiceImpl(CapitalService, BasicStockService):
    def __init__(self):
        super().__init__()

    def collect(self, symbols):
        symbols = self.build_symbols(symbols)
        self.collect_statement(symbols, 'p_stock2215', 'saa_capitals')
