import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = None


def get_job_class(data_type):
    from saa_collector.jobs.capital_collect_job import CapitalCollectJob
    from saa_collector.jobs.historical_price_collect_job import HistoricalPriceCollectJob
    from saa_collector.jobs.latest_price_collect_job import LatestPriceCollectJob
    from saa_collector.jobs.main_business_collect_job import MainBusinessCollectJob
    from saa_collector.jobs.statement_produce_job import StatementProduceJob
    from saa_collector.jobs.stock_info_collect_job import StockInfoCollectJob
    from saa_collector.jobs.valuation_collect_job import ValuationCollectJob

    job_mapping = {
        'stock_info': StockInfoCollectJob,
        'quote': LatestPriceCollectJob,
        'historical_quote': HistoricalPriceCollectJob,
        'balance_sheet': StatementProduceJob,
        'capital': CapitalCollectJob,
        'main_business': MainBusinessCollectJob,
        'valuation': ValuationCollectJob,
    }

    return job_mapping.get(data_type)


def init_scheduler():
    global scheduler

    if scheduler is not None:
        logger.warning('Scheduler already initialized')
        return

    scheduler = BackgroundScheduler()

    from .models import CollectSchedule
    schedules = CollectSchedule.objects.filter(status='ENABLED')

    for schedule in schedules:
        add_schedule_job(schedule)

    scheduler.start()
    logger.info(f'Scheduler started with {schedules.count()} enabled schedules')


def add_schedule_job(schedule):
    if scheduler is None:
        logger.error('Scheduler not initialized')
        return

    job_class = get_job_class(schedule.data_type)
    if job_class is None:
        logger.error(f'Unknown data_type: {schedule.data_type}')
        return

    try:
        job_instance = job_class(schedule.symbols if schedule.symbols else None)

        trigger = CronTrigger.from_crontab(schedule.cron_expression)

        job_id = f'schedule_{schedule.id}'
        scheduler.add_job(
            job_instance,
            trigger=trigger,
            id=job_id,
            replace_existing=True
        )

        logger.info(f'Added job {job_id} for schedule {schedule.name}')
    except Exception as e:
        logger.exception(f'Failed to add job for schedule {schedule.id}: {e}')


def remove_schedule_job(schedule_id):
    if scheduler is None:
        logger.error('Scheduler not initialized')
        return

    job_id = f'schedule_{schedule_id}'
    try:
        scheduler.remove_job(job_id)
        logger.info(f'Removed job {job_id}')
    except Exception as e:
        logger.warning(f'Failed to remove job {job_id}: {e}')


def update_schedule_job(schedule):
    remove_schedule_job(schedule.id)
    if schedule.status == 'ENABLED':
        add_schedule_job(schedule)
