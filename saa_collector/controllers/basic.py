from datetime import date, datetime, timedelta

from cement import Controller

from ..services.factory.compound_service_factory import CompoundServiceFactory


class Basic(Controller):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.service_factory = CompoundServiceFactory()

    def build_symbols(self):
        if not self.app.pargs.symbol:
            symbols = []
        else:
            symbols = self.app.pargs.symbol.split(',')
        return symbols

    def build_start_date(self):
        if not self.app.pargs.start_date:
            start_date = date.today() - timedelta(180)
        else:
            start_date = datetime.strptime(self.app.pargs.start_date, '%Y-%m-%d').date()
        return start_date
