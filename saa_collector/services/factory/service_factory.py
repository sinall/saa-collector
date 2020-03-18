# -*- coding: utf-8 -*-
from abc import abstractmethod


class ServiceFactory:
    @abstractmethod
    def create_calendar_service(self):
        pass

    @abstractmethod
    def create_stock_info_service(self):
        pass

    @abstractmethod
    def create_statement_service(self):
        pass

    @abstractmethod
    def create_capital_service(self):
        pass

    @abstractmethod
    def create_quote_service(self):
        pass
