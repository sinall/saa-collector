import logging
import threading
from datetime import datetime

from django import db
from django.db import connection
from django.utils import timezone

from saa_collector.constants import DATA_TYPE_CONFIG
from saa_collector.models import CollectJob, CollectPlan, DataIntegrityItem
from saa_collector.services.collect_execution_context import (
    get_collect_execution_context,
    reset_collect_execution_context,
    set_collect_execution_context,
)

logger = logging.getLogger(__name__)


def parse_period_to_date(period_str):
    if not period_str:
        return None
    if 'Q' in period_str:
        try:
            year = int(period_str[:4])
            quarter = int(period_str.split('Q')[1])
            end_month = quarter * 3
            end_day = 31 if end_month in [3, 12] else 30 if end_month in [4, 6, 9, 11] else 28
            return datetime.strptime(f"{year}-{end_month:02d}-{end_day}", '%Y-%m-%d').date()
        except (ValueError, IndexError):
            pass
    return datetime.strptime(period_str, '%Y-%m-%d').date()


def execute_plan(plan_id, task_id=None):
    db.connections.close_all()
    context_token = set_collect_execution_context(task_id=task_id, plan_id=plan_id)

    try:
        plan = CollectPlan.objects.get(id=plan_id)
        plan.status = 'RUNNING'
        plan.started_at = timezone.now()
        plan.completed_at = None
        plan.save()
        logger.info(
            'Starting collect plan: name=%s execution_mode=%s jobs=%d',
            plan.name,
            plan.execution_mode,
            plan.jobs.count(),
        )

        jobs = list(plan.jobs.all())

        if plan.execution_mode == 'PARALLEL':
            threads = []
            for job in jobs:
                t = threading.Thread(target=execute_job, args=(job.id, task_id, plan_id))
                t.start()
                threads.append(t)
            for t in threads:
                t.join()
        else:
            for job in jobs:
                execute_job(job.id, task_id, plan_id)

        plan.refresh_from_db()
        if plan.jobs.filter(status='FAILED').exists():
            plan.status = 'FAILED'
        else:
            plan.status = 'COMPLETED'
            update_report_items(plan)
        plan.completed_at = timezone.now()
        plan.save()
        logger.info('Finished collect plan: status=%s', plan.status)
    except Exception as e:
        logger.exception('Collect plan execution failed: %s', e)
        try:
            plan = CollectPlan.objects.get(id=plan_id)
            plan.status = 'FAILED'
            plan.completed_at = timezone.now()
            plan.save()
        except Exception:
            logger.exception('Failed to mark collect plan as failed')
        raise
    finally:
        reset_collect_execution_context(context_token)


def execute_job(job_id, task_id=None, plan_id=None):
    db.connections.close_all()

    try:
        job = CollectJob.objects.get(id=job_id)
        effective_plan_id = plan_id or job.plan_id
        context_token = set_collect_execution_context(
            task_id=task_id,
            plan_id=effective_plan_id,
            job_id=job.id,
            data_type=job.data_type,
        )
        job.start()
        logger.info('Starting collect job')
        execute_collect(job)
        job.complete(success=True, message='执行完成')
        logger.info('Finished collect job: status=SUCCESS')
    except Exception as e:
        logger.exception('Collect job execution failed: %s', e)
        try:
            job = CollectJob.objects.get(id=job_id)
            job.complete(success=False, message=str(e))
        except Exception:
            logger.exception('Failed to mark collect job as failed: job_id=%s', job_id)
    finally:
        if 'context_token' in locals():
            reset_collect_execution_context(context_token)


def execute_collect(job):
    from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory

    factory = CompoundServiceFactory()
    data_type = job.data_type
    symbols = job.config.get('symbols') if job.config.get('symbols') else None
    params = job.config.get('params', {})
    start_date = job.config.get('start_date') or params.get('start_date')
    end_date = job.config.get('end_date') or params.get('end_date')

    if start_date:
        start_date = parse_period_to_date(start_date)
    if end_date:
        end_date = parse_period_to_date(end_date)

    unit = 'symbol' if data_type in (
        'stock_info', 'quote', 'historical_quote', 'financial_statements',
        'balance_sheet', 'income', 'cash_flow', 'dividend', 'capital',
        'main_business'
    ) else 'job'
    unit_context = get_collect_execution_context()
    unit_context_token = set_collect_execution_context(**unit_context, unit=unit)
    logger.info(
        'Collecting: symbols=%s start_date=%s end_date=%s',
        symbols,
        start_date,
        end_date,
    )
    try:
        if data_type == 'trade_days':
            service = factory.create_calendar_service()
            service.collect(start_date, end_date)
        elif data_type == 'stock_info':
            service = factory.create_stock_info_service()
            service.collect(symbols)
        elif data_type == 'quote':
            service = factory.create_quote_service()
            service.collect(symbols)
        elif data_type == 'historical_quote':
            service = factory.create_quote_service()
            service.collect_historical(symbols, start_date=start_date, end_date=end_date)
        elif data_type == 'financial_statements':
            service = factory.create_statement_service()
            service.produce(symbols, start_date)
        elif data_type in ('balance_sheet', 'income', 'cash_flow', 'dividend'):
            service = factory.create_statement_service()
            report_types = params.get('report_types', [])
            if data_type == 'balance_sheet' or 'balance_sheet' in report_types:
                service.collect_balance_sheet(symbols, start_date)
            if data_type == 'income' or 'income' in report_types:
                service.collect_income(symbols, start_date)
            if data_type == 'cash_flow' or 'cash_flow' in report_types:
                service.collect_cash_flow(symbols, start_date)
            if data_type == 'dividend' or 'dividend' in report_types:
                service.collect_dividend(symbols, start_date)
        elif data_type == 'capital':
            service = factory.create_capital_service()
            service.collect(symbols, start_date)
        elif data_type == 'main_business':
            service = factory.create_statement_service()
            service.collect_main_business(symbols, start_date)
        elif data_type == 'valuation':
            from saa_collector.jobs.valuation_collect_job import ValuationCollectJob
            collect_job = ValuationCollectJob()
            collect_job()
        elif data_type == 'tick':
            from saa_collector.jobs.tick_job import TickJob
            collect_job = TickJob()
            collect_job()
        else:
            logger.warning(f"[Job {job.id}] Unknown data type: {data_type}")
    finally:
        reset_collect_execution_context(unit_context_token)


def update_report_items(plan):
    if not plan.source_report:
        return

    successful_jobs = plan.jobs.filter(status='SUCCESS')
    for job in successful_jobs:
        symbols = job.config.get('symbols', [])
        miss_periods = job.config.get('miss_periods', [])

        if not symbols:
            continue

        if not miss_periods:
            DataIntegrityItem.objects.filter(
                report=plan.source_report,
                data_type=job.data_type,
                stock_code__in=symbols,
                status='PENDING'
            ).update(
                status='FIXED',
                fixed_at=timezone.now(),
                fixed_by_plan=plan
            )
            logger.info(f"[Job {job.id}] Marked all items as FIXED for data_type={job.data_type}")
            continue

        fixed_count = 0
        for symbol in symbols:
            for period in miss_periods:
                if verify_data_exists(job.data_type, symbol, period):
                    updated = DataIntegrityItem.objects.filter(
                        report=plan.source_report,
                        data_type=job.data_type,
                        stock_code=symbol,
                        miss_period=period,
                        status='PENDING'
                    ).update(
                        status='FIXED',
                        fixed_at=timezone.now(),
                        fixed_by_plan=plan
                    )
                    if updated > 0:
                        fixed_count += 1
                        logger.info(f"[Job {job.id}] Verified and fixed: {symbol} - {period}")
                else:
                    logger.warning(f"[Job {job.id}] Data not found in DB: {symbol} - {period}, skip marking as FIXED")

        logger.info(f"[Job {job.id}] Fixed {fixed_count} items after verification")


def verify_data_exists(data_type, symbol, period):
    if data_type not in DATA_TYPE_CONFIG:
        logger.warning(f"Unknown data_type: {data_type}")
        return False

    config = DATA_TYPE_CONFIG[data_type]
    table_name = config['table']
    date_column = config['date_column']
    stock_column = config.get('stock_column', 'symbol')

    if not date_column:
        return False

    period_date = parse_period_to_date(period)
    if not period_date:
        logger.warning(f"Invalid period format: {period}")
        return False

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM {table_name} "
                f"WHERE {stock_column} = %s AND {date_column} = %s",
                [symbol, period_date]
            )
            count = cursor.fetchone()[0]
            exists = count > 0
            if not exists:
                logger.debug(f"No data found in {table_name}: {stock_column}={symbol}, {date_column}={period_date}")
            return exists
    except Exception as e:
        logger.exception(f"Error verifying data existence: {e}")
        return False
