# -*- coding: utf-8 -*-

from .basic_stock_collect_job import BasicStockCollectJob


class StatementCollectJob(BasicStockCollectJob):
    def __init__(self, symbols=None):
        super().__init__(symbols)
        if symbols is None:
            symbols = []
        self.symbols = symbols
        self.statement_service = self.service_factory.create_statement_service()

    def __call__(self):
        self.statement_service.collect(self.symbols, self.build_start_date())
