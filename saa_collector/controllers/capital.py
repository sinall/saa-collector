from cement import ex
from cement.utils.version import get_version_banner

from .basic import Basic
from ..core.version import get_version

VERSION_BANNER = """
Collect SAA related data like stock basic data, financial data, etc. %s
%s
""" % (get_version(), get_version_banner())


class Capital(Basic):
    class Meta:
        label = 'capital'
        stacked_type = 'embedded'
        stacked_on = 'base'

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.capital_service = self.service_factory.create_capital_service()

    @ex(
        help='example sub collect-capital',
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
    def collect_capital(self):
        symbols = self.build_symbols()
        start_date = self.build_start_date()
        self.capital_service.collect(symbols, start_date)

        data = {
            'symbol': self.app.pargs.symbol,
            'count': len(symbols),
        }
        self.app.render(data, 'collect_stocks.jinja2')
