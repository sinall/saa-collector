import argparse
import logging
import logging.config
import os
import time

from apscheduler.schedulers.background import BackgroundScheduler

from saa_collector.jobs.capital_collect_job import CapitalCollectJob
from saa_collector.jobs.historical_price_collect_job import HistoricalPriceCollectJob
from saa_collector.jobs.latest_price_collect_job import LatestPriceCollectJob
from saa_collector.jobs.main_business_collect_job import MainBusinessCollectJob
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
        scheduler.add_job(TickJob(), APCronParser.parse('*/10 * * * *'))
        scheduler.add_job(StockInfoCollectJob(symbols), APCronParser.parse('5 1 1 * *'))
        scheduler.add_job(StatementProduceJob(symbols), APCronParser.parse('5 0 7 5 *'))
        scheduler.add_job(StatementProduceJob(symbols), APCronParser.parse('5 0 7 9 *'))
        scheduler.add_job(StatementProduceJob(symbols), APCronParser.parse('5 0 7 11 *'))
        scheduler.add_job(CapitalCollectJob(symbols), APCronParser.parse('5 0 7 * *'))
        scheduler.add_job(MainBusinessCollectJob(symbols), APCronParser.parse('5 0 9 5 *'))
        scheduler.add_job(LatestPriceCollectJob(symbols), APCronParser.parse('00 16 * * MON-FRI'))
        scheduler.add_job(HistoricalPriceCollectJob(symbols), APCronParser.parse('5 0 1 * *'))
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
