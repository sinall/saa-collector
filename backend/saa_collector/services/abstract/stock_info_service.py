# -*- coding: utf-8 -*-
from abc import abstractmethod


class StockInfoService:
    @abstractmethod
    def collect(self, symbols):
        pass

    @abstractmethod
    def build_symbols(self, symbols):
        pass

    @abstractmethod
    def get_stock_info_list(self, scode_list):
        pass
