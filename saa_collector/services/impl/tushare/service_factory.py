# -*- coding: utf-8 -*-
from saa_collector.services.factory.service_factory import ServiceFactory
from saa_collector.services.impl.tushare.capital_service import CapitalServiceImpl
from saa_collector.services.impl.tushare.quote_service import QuoteServiceImpl
from saa_collector.services.impl.tushare.statement_service import StatementServiceImpl
from saa_collector.services.impl.tushare.stock_info_service import StockInfoServiceImpl


class TushareServiceFactoryImpl(ServiceFactory):
    def create_stock_info_service(self):
        return StockInfoServiceImpl()

    def create_statement_service(self):
        return StatementServiceImpl()

    def create_capital_service(self):
        return CapitalServiceImpl()

    def create_quote_service(self):
        return QuoteServiceImpl()
