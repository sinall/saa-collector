# -*- coding: utf-8 -*-

from .basic_stock_collect_job import BasicStockCollectJob
from ..services.factory.compound_service_factory import CompoundServiceFactory


class LatestPriceCollectJob(BasicStockCollectJob):
    def __init__(self, symbols=None):
        super().__init__(symbols)
        if symbols is None:
            symbols = []
        self.symbols = symbols
        service_factory = CompoundServiceFactory()
        self.quote_service = service_factory.create_quote_service()

    def __call__(self):
        self.quote_service.collect(self.symbols)
