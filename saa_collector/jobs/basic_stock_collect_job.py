# -*- coding: utf-8 -*-

from saa_collector.jobs.basic_job import BasicJob
from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory


class BasicStockCollectJob(BasicJob):
    def __init__(self, symbols=None):
        super().__init__()
        if symbols is None:
            symbols = []
        self.symbols = symbols
        self.service_factory = CompoundServiceFactory()
        self.stock_service = self.service_factory.create_stock_info_service()

    def __call__(self):
        self.stock_service.collect(self.symbols)
