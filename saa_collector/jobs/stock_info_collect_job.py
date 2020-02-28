# -*- coding: utf-8 -*-

from .basic_stock_collect_job import BasicStockCollectJob
from ..services.stock_info_service import StockInfoService


class StockInfoCollectJob(BasicStockCollectJob):
    def __init__(self, symbols=None):
        super().__init__()
        if symbols is None:
            symbols = []
        self.symbols = symbols
        self.stock_service = StockInfoService()

    def __call__(self):
        self.stock_service.collect(self.symbols)
