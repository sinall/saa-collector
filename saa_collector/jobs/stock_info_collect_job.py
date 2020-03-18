# -*- coding: utf-8 -*-

from .basic_stock_collect_job import BasicStockCollectJob
from ..services.factory.compound_service_factory import CompoundServiceFactory


class StockInfoCollectJob(BasicStockCollectJob):
    def __init__(self, symbols=None):
        super().__init__()
        if symbols is None:
            symbols = []
        self.symbols = symbols
        service_factory = CompoundServiceFactory()
        self.stock_service = service_factory.create_stock_info_service()

    def __call__(self):
        self.stock_service.collect(self.symbols)
