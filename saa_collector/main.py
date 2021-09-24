from os.path import join

from cement import App, TestApp, init_defaults
from cement.core.exc import CaughtSignal

from saa_collector.controllers.base import Base
from saa_collector.controllers.capital import Capital
from saa_collector.controllers.quote import Quote
from saa_collector.controllers.statement import Statement
from saa_collector.controllers.stock import Stock
from saa_collector.controllers.valudation import Valuation
from saa_collector.core.exc import SaaCollectorError
from saa_collector.utils.log import LoggingInitializer

# configuration defaults
CONFIG = init_defaults('saa_collector')
CONFIG['saa_collector']['foo'] = 'bar'
CONFIG['saa_collector']['symbol'] = '000001'


class SaaCollector(App):
    """SAA Collector primary application."""

    class Meta:
        label = 'saa_collector'

        # configuration defaults
        config_defaults = CONFIG

        # call sys.exit() on close
        exit_on_close = True

        # load additional framework extensions
        extensions = [
            'yaml',
            'colorlog',
            'jinja2',
        ]

        # configuration handler
        config_handler = 'yaml'

        # configuration file suffix
        config_file_suffix = '.yml'

        # set the log handler
        log_handler = 'colorlog'

        # set the output handler
        output_handler = 'jinja2'

        # register handlers
        handlers = [
            Base,
            Stock,
            Statement,
            Capital,
            Quote,
            Valuation,
        ]


class SaaCollectorTest(TestApp, SaaCollector):
    """A sub-class of SaaCollector that is better suited for testing."""

    class Meta:
        label = 'saa_collector'

        core_user_config_files = [
            join('{home_dir}', '.{label}', 'config', '{label}{suffix}'),
        ]


def main():
    LoggingInitializer.init()

    with SaaCollector() as app:
        try:
            app.run()

        except AssertionError as e:
            print('AssertionError > %s' % e.args[0])
            app.exit_code = 1

            if app.debug is True:
                import traceback
                traceback.print_exc()

        except SaaCollectorError as e:
            print('SaaCollectorError > %s' % e.args[0])
            app.exit_code = 1

            if app.debug is True:
                import traceback
                traceback.print_exc()

        except CaughtSignal as e:
            # Default Cement signals are SIGINT and SIGTERM, exit 0 (non-error)
            print('\n%s' % e)
            app.exit_code = 0


if __name__ == '__main__':
    main()
