# -*- coding: utf-8 -*-
from abc import abstractmethod


class StatementService:
    @abstractmethod
    def produce(self, symbols):
        pass

    @abstractmethod
    def process(self, symbols):
        pass

    @abstractmethod
    def collect(self, symbols):
        pass

    @abstractmethod
    def collect_balance_sheet(self, symbols):
        pass

    @abstractmethod
    def collect_income(self, symbols):
        pass

    @abstractmethod
    def collect_cash_flow(self, symbols):
        pass

    @abstractmethod
    def collect_dividend(self, symbols):
        pass
