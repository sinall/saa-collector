# -*- coding: utf-8 -*-

from saa_collector.services.factory.service_factory import ServiceFactory
from saa_collector.services.impl.cninfo.service_factory import CninfoServiceFactoryImpl
from saa_collector.services.impl.tushare.service_factory import TushareServiceFactoryImpl


class CompoundServiceFactory(ServiceFactory):
    def __init__(self):
        self.cninfo_impl = CninfoServiceFactoryImpl()
        self.tushare_impl = TushareServiceFactoryImpl()
        self.impl = self.tushare_impl

    def create_calendar_service(self):
        return self.impl.create_calendar_service()

    def create_stock_info_service(self):
        return self.impl.create_stock_info_service()

    def create_statement_service(self):
        return self.impl.create_statement_service()

    def create_capital_service(self):
        return self.impl.create_capital_service()

    def create_quote_service(self):
        return self.impl.create_quote_service()
