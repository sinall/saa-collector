# -*- coding: utf-8 -*-

from saa_collector.services.abstract.capital_service import CapitalService
from .basic_stock_service import BasicStockService
import akshare as ak

from ...common.stock_utils import StockUtils


class CapitalServiceImpl(CapitalService, BasicStockService):
    def __init__(self):
        super().__init__()

    def collect(self, symbols, start_date=None):
        symbols = self.build_symbols(symbols)
        sub_resource = 'capital'
        table = self._get_table(sub_resource)
        df = self.query(sub_resource, symbols, self.channel, start_date)
        records = df.to_dict('records')
        self.save_records(records, table, ['symbol', 'date'])

    def query_one(self, sub_resource, symbol, **kwargs):
        df = ak.stock_zh_a_gbjg_em(symbol=self.to_code(symbol))
        return df

    def to_code(self, symbol):
        code = '{}.{}'.format(symbol, str(StockUtils.to_exchange(symbol)))
        return code
