# -*- coding: utf-8 -*-
from abc import abstractmethod


class StatementService:
    @abstractmethod
    def produce(self, symbols, start_date=None):
        pass

    @abstractmethod
    def process(self, symbols, start_date=None):
        pass

    @abstractmethod
    def collect(self, symbols, start_date=None):
        pass

    @abstractmethod
    def collect_balance_sheet(self, symbols, start_date=None):
        pass

    @abstractmethod
    def collect_income(self, symbols, start_date=None):
        pass

    @abstractmethod
    def collect_cash_flow(self, symbols, start_date=None):
        pass

    @abstractmethod
    def collect_dividend(self, symbols, start_date=None):
        pass

    @abstractmethod
    def collect_main_business(self, symbols, start_date=None):
        pass
