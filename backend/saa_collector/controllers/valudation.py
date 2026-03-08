from datetime import datetime, date

from cement import ex
from cement.utils.version import get_version_banner

from .basic import Basic
from ..core.version import get_version

VERSION_BANNER = """
Collect valuation data. %s
%s
""" % (get_version(), get_version_banner())


class Valuation(Basic):
    class Meta:
        label = 'valuation'
        stacked_type = 'embedded'
        stacked_on = 'base'

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.valuation_service = self.service_factory.create_valuation_service()

    @ex(
        help='example sub collect-valuation',
        arguments=[
            (['--date'],
             {'help': 'notorious date option',
              'action': 'store',
              'dest': 'date'}),
        ],
    )
    def collect_valuation(self):
        date_arg = self.build_date()
        self.valuation_service.collect(date_arg)

    def build_date(self):
        if not self.app.pargs.date:
            date_arg = date.today()
        else:
            date_arg = datetime.strptime(self.app.pargs.date, '%Y-%m-%d').date()
        return date_arg
