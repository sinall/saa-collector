import logging
from datetime import datetime

from cement import ex
from cement.utils.version import get_version_banner

from .basic import Basic
from ..core.version import get_version

VERSION_BANNER = """
Collect quotation data, etc. %s
%s
""" % (get_version(), get_version_banner())


class Quote(Basic):
    class Meta:
        label = 'quote'
        stacked_type = 'embedded'
        stacked_on = 'base'

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._logger = logging.getLogger()
        self.quote_service = self.service_factory.create_quote_service()

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
        symbols = self.build_symbols()
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
             {'help': 'notorious date option',
              'action': 'store',
              'dest': 'date'}),
            (['--start-date'],
             {'help': 'notorious start-date option',
              'action': 'store',
              'dest': 'start_date'}),
        ],
    )
    def collect_historical_price(self):
        symbols = self.build_symbols()
        start_date = self.build_start_date()
        cal_date = datetime.strptime(self.app.pargs.date, '%Y-%m-%d')
        self.quote_service.collect_historical(symbols, cal_date, start_date)

        data = {
            'symbol': self.app.pargs.symbol,
            'count': len(symbols),
        }
        self.app.render(data, 'collect_stocks.jinja2')
