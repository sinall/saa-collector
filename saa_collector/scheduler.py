import argparse
import logging
import logging.config
import os
import time

from apscheduler.schedulers.background import BackgroundScheduler

from saa_collector.jobs.capital_collect_job import CapitalCollectJob
from saa_collector.jobs.statement_produce_job import StatementProduceJob
from saa_collector.jobs.stock_info_collect_job import StockInfoCollectJob
from saa_collector.jobs.tick_job import TickJob
from saa_collector.utils.ap import APCronParser
from saa_collector.utils.log import LoggingInitializer


class Scheduler(object):
    def __init__(self):
        self._logger = logging.getLogger()

    def start(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-s', dest='symbol_arg', action='store')
        parser.add_argument('--symbol', dest='symbol_arg', action='store')
        args = parser.parse_args()
        symbols = None
        if args.symbol_arg:
            symbols = args.symbol_arg.split(',')

        scheduler = BackgroundScheduler()
        scheduler.add_job(TickJob(), APCronParser.parse('0 0/1 * * * * * *'))
        scheduler.add_job(StockInfoCollectJob(symbols), APCronParser.parse('0 5 1 1 * ? * *'))
        scheduler.add_job(StatementProduceJob(symbols), APCronParser.parse('0 5 0 ? 5 7 * *'))
        scheduler.add_job(StatementProduceJob(symbols), APCronParser.parse('0 5 0 ? 9 7 * *'))
        scheduler.add_job(StatementProduceJob(symbols), APCronParser.parse('0 5 0 ? 11 7 * *'))
        scheduler.add_job(CapitalCollectJob(symbols), APCronParser.parse('0 5 0 ? * SAT * *'))
        scheduler.start()
        self._logger.info('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))

        try:
            while True:
                time.sleep(2)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()


def main():
    LoggingInitializer.init()

    Scheduler().start()


if __name__ == '__main__':
    main()
