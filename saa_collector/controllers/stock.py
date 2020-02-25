from cement import Controller, ex
from cement.utils.version import get_version_banner

from ..core.version import get_version
from ..services.stock_info_service import StockInfoService

VERSION_BANNER = """
Collect stock basic data, etc. %s
%s
""" % (get_version(), get_version_banner())


class Stock(Controller):
    class Meta:
        label = 'stock'
        stacked_type = 'embedded'
        stacked_on = 'base'

    @ex(
        help='example sub collect-stocks',
        arguments=[
            (['-s', '--symbol'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'symbol'}),
        ],
    )
    def collect_stocks(self):
        symbols = self.parse_symbols()
        stock_service = StockInfoService()
        stock_service.collect(symbols)

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
