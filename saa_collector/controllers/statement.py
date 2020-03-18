from cement import Controller, ex
from cement.utils.version import get_version_banner

from ..core.version import get_version
from ..services.factory.compound_service_factory import CompoundServiceFactory

VERSION_BANNER = """
Collect financial data, etc. %s
%s
""" % (get_version(), get_version_banner())


class Statement(Controller):
    class Meta:
        label = 'statement'
        stacked_type = 'embedded'
        stacked_on = 'base'

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        service_factory = CompoundServiceFactory()
        self.statement_service = service_factory.create_statement_service()

    @ex(
        help='example sub produce-all-statements',
        arguments=[
            (['-s', '--symbol'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'symbol'}),
        ],
    )
    def produce_all_statements(self):
        symbols = self.parse_symbols()
        self.statement_service.produce(symbols)

        data = {
            'symbol': self.app.pargs.symbol,
            'count': len(symbols),
        }
        self.app.render(data, 'collect_stocks.jinja2')

    @ex(
        help='example sub collect-all-statements',
        arguments=[
            (['-s', '--symbol'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'symbol'}),
        ],
    )
    def collect_all_statements(self):
        symbols = self.parse_symbols()
        self.statement_service.collect(symbols)

        data = {
            'symbol': self.app.pargs.symbol,
            'count': len(symbols),
        }
        self.app.render(data, 'collect_stocks.jinja2')

    @ex(
        help='example sub collect-capital',
        arguments=[
            (['-s', '--symbol'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'symbol'}),
        ],
    )
    def collect_capital(self):
        symbols = self.parse_symbols()
        self.statement_service.collect(symbols)

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
