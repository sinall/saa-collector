# -*- coding: utf-8 -*-
from abc import abstractmethod


class QuoteService:
    @abstractmethod
    def collect(self, symbols=None):
        pass

    @abstractmethod
    def collect_historical(self, symbols=None, trade_date=None, start_date=None, end_date=None):
        pass
