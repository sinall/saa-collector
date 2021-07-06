# -*- coding: utf-8 -*-

from .basic_stock_collect_job import BasicStockCollectJob


class CapitalCollectJob(BasicStockCollectJob):
    def __init__(self, symbols=None):
        super().__init__(symbols)
        if symbols is None:
            symbols = []
        self.symbols = symbols
        self.capital_service = self.service_factory.create_capital_service()

    def __call__(self):
        self.capital_service.collect(self.symbols)
