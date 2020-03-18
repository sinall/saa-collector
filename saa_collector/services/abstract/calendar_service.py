# -*- coding: utf-8 -*-
from abc import abstractmethod


class CalendarService:
    @abstractmethod
    def get_last_trade_day_monthly(self, exchange=None, start_date=None, end_date=None, is_open='1'):
        pass

    @abstractmethod
    def get_last_day_of_previous_month(self):
        pass
