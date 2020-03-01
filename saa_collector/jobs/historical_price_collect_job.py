# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from .basic_stock_collect_job import BasicStockCollectJob
from ..services.calendar_service import CalendarService
from ..services.quotation_service import QuotationService


class HistoricalPriceCollectJob(BasicStockCollectJob):
    def __init__(self, symbols=None):
        super().__init__(symbols)
        if symbols is None:
            symbols = []
        self.symbols = symbols
        self.calendar_service = CalendarService()
        self.quotation_service = QuotationService()

    def __call__(self):
        cal_date = self.calendar_service.get_last_day_of_previous_month()
        self.quotation_service.collect_historical(None, cal_date)
