from cement import ex
from cement.utils.version import get_version_banner

from .basic import Basic
from ..core.version import get_version

VERSION_BANNER = """
Collect financial data, etc. %s
%s
""" % (get_version(), get_version_banner())


class Statement(Basic):
    class Meta:
        label = 'statement'
        stacked_type = 'embedded'
        stacked_on = 'base'

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.statement_service = self.service_factory.create_statement_service()

    @ex(
        help='example sub produce-all-statements',
        arguments=[
            (['-s', '--symbol'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'symbol'}),
            (['--start-date'],
             {'help': 'notorious symbol option',
              'action': 'store',
              'dest': 'start_date'}),
        ],
    )
    def produce_all_statements(self):
        symbols = self.build_symbols()
        start_date = self.build_start_date()
        self.statement_service.produce(symbols, start_date)

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
            (['--start-date'],
             {'help': 'notorious start-date option',
              'action': 'store',
              'dest': 'start_date'}),
        ],
    )
    def collect_all_statements(self):
        symbols = self.build_symbols()
        start_date = self.build_start_date()
        self.statement_service.collect(symbols, start_date)

        data = {
            'symbol': self.app.pargs.symbol,
            'count': len(symbols),
        }
        self.app.render(data, 'collect_stocks.jinja2')
