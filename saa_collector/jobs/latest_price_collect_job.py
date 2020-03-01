# -*- coding: utf-8 -*-

from .basic_stock_collect_job import BasicStockCollectJob
from ..services.quotation_service import QuotationService


class LatestPriceCollectJob(BasicStockCollectJob):
    def __init__(self, symbols=None):
        super().__init__(symbols)
        if symbols is None:
            symbols = []
        self.symbols = symbols
        self.quotation_service = QuotationService()

    def __call__(self):
        self.quotation_service.collect(self.symbols)
