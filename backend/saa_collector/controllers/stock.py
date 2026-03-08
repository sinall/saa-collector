from cement import ex
from cement.utils.version import get_version_banner

from .basic import Basic
from ..core.version import get_version

VERSION_BANNER = """
Collect stock basic data, etc. %s
%s
""" % (get_version(), get_version_banner())


class Stock(Basic):
    class Meta:
        label = 'stock'
        stacked_type = 'embedded'
        stacked_on = 'base'

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.stock_service = self.service_factory.create_stock_info_service()

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
        symbols = self.build_symbols()
        self.stock_service.collect(symbols)

        data = {
            'symbol': self.app.pargs.symbol,
            'count': len(symbols),
        }
        self.app.render(data, 'collect_stocks.jinja2')

    def build_symbols(self):
        if not self.app.pargs.symbol:
            symbols = []
        else:
            symbols = self.app.pargs.symbol.split(',')
        return symbols
