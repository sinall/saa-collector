# -*- coding: utf-8 -*-

from saa_collector.jobs.basic_job import BasicJob
from ..services.stock_info_service import StockInfoService


class BasicStockCollectJob(BasicJob):
    def __init__(self, symbols=None):
        super().__init__()
        if symbols is None:
            symbols = []
        self.symbols = symbols
        self.stock_service = StockInfoService()

    def __call__(self):
        self.stock_service.collect(self.symbols)
