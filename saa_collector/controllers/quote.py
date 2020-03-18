import logging
from datetime import datetime

from cement import Controller, ex
from cement.utils.version import get_version_banner

from ..core.version import get_version
from ..services.factory.compound_service_factory import CompoundServiceFactory

VERSION_BANNER = """
Collect quotation data, etc. %s
%s
""" % (get_version(), get_version_banner())


class Quote(Controller):
    class Meta:
        label = 'quote'
        stacked_type = 'embedded'
        stacked_on = 'base'

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._logger = logging.getLogger()
        service_factory = CompoundServiceFactory()
        self.quote_service = service_factory.create_stock_info_service()

    @ex(
        help='example sub collect-price',
        arguments=[
            (['-s', '--symbol'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'symbol'}),
        ],
    )
    def collect_price(self):
        self._logger.info("Start to collect prices")
        symbols = self.parse_symbols()
        self.quote_service.collect(symbols)

        data = {
            'symbol': self.app.pargs.symbol,
            'count': len(symbols),
        }
        self.app.render(data, 'collect_stocks.jinja2')

    @ex(
        help='example sub collect-historical-price',
        arguments=[
            (['-s', '--symbol'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'symbol'}),
            (['-d', '--date'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'date'}),
        ],
    )
    def collect_historical_price(self):
        symbols = self.parse_symbols()
        cal_date = datetime.strptime(self.app.pargs.date, '%Y-%m-%d')
        self.quote_service.collect_historical(None, cal_date)

        data = {
            'symbol': self.app.pargs.symbol,
            'count': len(symbols),
        }
        self.app.render(data, 'collect_stocks.jinja2')

    def parse_symbols(self):
        if not self.app.pargs.symbol:
            symbols = []
        else:
            symbols = self.app.pargs.symbol.split(',')
        return symbols
