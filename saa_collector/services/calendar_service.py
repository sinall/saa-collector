# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from saa_collector.services.basic_stock_service import BasicStockService


class CalendarService(BasicStockService):
    BATCH_SIZE = 50

    def __init__(self):
        super().__init__()

    def get_last_trade_day_monthly(self, exchange=None, start_date=None, end_date=None, is_open='1'):
        last_day_of_previous_month = self.get_last_day_of_previous_month()
        end_date = datetime.today()
        start_date = end_date - timedelta(days=45)
        df = self.pro.trade_cal(
            exchange=exchange,
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d'),
            is_open=is_open
        )
        cal_dates = df['cal_date'].tolist()
        cal_dates = [datetime.strptime(d, '%Y%m%d') for d in cal_dates]
        cal_dates = [d for d in cal_dates if d <= last_day_of_previous_month]
        last_trade_day = max(cal_dates)
        return last_trade_day

    def get_last_day_of_previous_month(self):
        today = datetime.today()
        first = today.replace(day=1)
        last_month = first - timedelta(days=1)
        return last_month


if __name__ == '__main__':
    CalendarService().get_last_trade_day_monthly('SSE')
