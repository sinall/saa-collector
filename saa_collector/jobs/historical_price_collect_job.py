# -*- coding: utf-8 -*-

from saa_collector.services.abstract.calendar_service import CalendarService
from .basic_stock_collect_job import BasicStockCollectJob


class HistoricalPriceCollectJob(BasicStockCollectJob):
    def __init__(self, symbols=None):
        super().__init__(symbols)
        if symbols is None:
            symbols = []
        self.symbols = symbols
        self.calendar_service = CalendarService()
        self.quote_service = self.service_factory.create_quote_service()

    def __call__(self):
        cal_date = self.calendar_service.get_last_day_of_previous_month()
        self.quote_service.collect_historical(None, cal_date)
