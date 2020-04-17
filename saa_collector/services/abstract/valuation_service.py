# -*- coding: utf-8 -*-
from abc import abstractmethod


class ValuationService:
    @abstractmethod
    def collect(self, date=None):
        pass
    @abstractmethod
    def collect_board(self, date=None):
        pass

    @abstractmethod
    def collect_industry(self, date=None):
        pass
