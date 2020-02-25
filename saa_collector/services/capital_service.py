# -*- coding: utf-8 -*-

from .basic_stock_service import BasicStockService


class CapitalService(BasicStockService):
    def __init__(self):
        super().__init__()

    def collect(self, symbols):
        symbols = self.build_symbols(symbols)
        self.collect_statement(symbols, 'p_stock2215', 'saa_capitals')
