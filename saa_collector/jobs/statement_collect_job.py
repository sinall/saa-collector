# -*- coding: utf-8 -*-

from .basic_stock_collect_job import BasicStockCollectJob
from ..services.statement_service import StatementService


class StatementCollectJob(BasicStockCollectJob):
    def __init__(self, symbols=None):
        super().__init__(symbols)
        if symbols is None:
            symbols = []
        self.symbols = symbols
        self.statement_service = StatementService()

    def __call__(self):
        self.statement_service.collect(self.symbols)
