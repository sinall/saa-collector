# -*- coding: utf-8 -*-

from .basic_stock_collect_job import BasicStockCollectJob


class StockInfoCollectJob(BasicStockCollectJob):
    def __init__(self, symbols=None):
        super().__init__()
        if symbols is None:
            symbols = []
        self.symbols = symbols
        self.stock_service = self.service_factory.create_stock_info_service()

    def __call__(self):
        self.stock_service.collect(self.symbols)
