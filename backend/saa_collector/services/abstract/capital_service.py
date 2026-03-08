# -*- coding: utf-8 -*-
from abc import abstractmethod


class CapitalService:
    @abstractmethod
    def collect(self, symbols, start_date=None):
        pass
