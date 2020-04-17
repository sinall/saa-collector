# -*- coding: utf-8 -*-
from datetime import datetime

from .basic_stock_collect_job import BasicStockCollectJob


class ValuationCollectJob(BasicStockCollectJob):
    def __init__(self):
        super().__init__()
        self.valuation_service = self.service_factory.create_valuation_service()

    def __call__(self):
        date = datetime.today()
        self.valuation_service.collect(date)
