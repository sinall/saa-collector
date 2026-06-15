# -*- coding: utf-8 -*-
import logging

from saa_collector.services.common.valuation_service import ValuationServiceImpl
from saa_collector.services.factory.service_factory import ServiceFactory
from saa_collector.services.factory.provider_config import build_selection, resolve_provider
from saa_collector.services.impl.akshare.service_factory import AkshareServiceFactoryImpl
from saa_collector.services.impl.cninfo.service_factory import CninfoServiceFactoryImpl
from saa_collector.services.impl.tushare.service_factory import TushareServiceFactoryImpl

logger = logging.getLogger(__name__)


class CompoundServiceFactory(ServiceFactory):
    def __init__(self, data_type=None, provider=None, provider_source=None):
        self.akshare_impl = AkshareServiceFactoryImpl()
        self.cninfo_impl = CninfoServiceFactoryImpl()
        self.tushare_impl = TushareServiceFactoryImpl()

        selection = (
            resolve_provider(data_type)
            if provider is None
            else build_selection(provider, provider_source or 'explicit')
        )
        data_source = selection.provider
        provider_source = selection.source
        if data_source == 'akshare':
            self.impl = self.akshare_impl
        else:
            self.impl = self.tushare_impl
        logger.info(
            'CompoundServiceFactory initialized: data_type=%s provider=%s source=%s selected_impl=%s',
            data_type,
            data_source,
            provider_source,
            self.impl.__class__.__name__,
        )

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

    def create_valuation_service(self):
        return ValuationServiceImpl()
