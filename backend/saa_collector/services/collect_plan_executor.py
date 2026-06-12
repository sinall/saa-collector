import logging
import threading
import ctypes
import gc
from datetime import date, datetime, timedelta

from django import db
from django.db import connection, transaction
from django.utils import timezone

from saa_collector.collect_job_config import get_cache_control
from saa_collector.constants import DATA_TYPE_CONFIG
from saa_collector.date_expressions import (
    normalize_schedule_params,
    resolve_schedule_date_range,
)
from saa_collector.models import CollectJob, CollectPlan, DataIntegrityItem
from saa_collector.services.collect_execution_context import (
    get_collect_execution_context,
    reset_collect_execution_context,
    set_collect_execution_context,
)
from saa_collector.services.common.progress import ProgressLogger

logger = logging.getLogger(__name__)


REMAINING_SYMBOLS_KEY = 'remaining_symbols'
COMPLETED_SYMBOLS_KEY = 'completed_symbols'
FAILED_SYMBOLS_KEY = 'failed_symbols'
SKIP_EXISTING_SUMMARY_KEY = 'skip_existing_summary'


class PlanExecutionStopped(RuntimeError):
    pass


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
        with transaction.atomic():
            plan = CollectPlan.objects.select_for_update().get(id=plan_id)
            if plan.status == 'STOPPED':
                logger.info('Collect plan %s already stopped before execution starts', plan.id)
                return
            plan.status = 'RUNNING'
            if plan.started_at is None:
                plan.started_at = timezone.now()
            plan.completed_at = None
            plan.save()
        logger.info(
            'Starting collect plan: name=%s execution_mode=%s jobs=%d',
            plan.name,
            plan.execution_mode,
            plan.jobs.count(),
        )

        jobs = list(plan.jobs.exclude(status='SUCCESS'))

        if plan.execution_mode == 'PARALLEL':
            threads = []
            for job in jobs:
                ensure_plan_not_stopped(plan_id)
                t = threading.Thread(target=execute_job, args=(job.id, task_id, plan_id))
                t.start()
                threads.append(t)
            for t in threads:
                t.join()
        else:
            for job in jobs:
                ensure_plan_not_stopped(plan_id)
                execute_job(job.id, task_id, plan_id)

        refresh_django_db_connections('before plan finalization')
        plan.refresh_from_db()
        if plan.status == 'STOPPED':
            logger.info('Collect plan %s stopped before finalization', plan.id)
            return
        if plan.jobs.filter(status='FAILED').exists():
            plan.status = 'FAILED'
        else:
            plan.status = 'COMPLETED'
            update_report_items(plan)
        plan.completed_at = timezone.now()
        plan.save()
        logger.info('Finished collect plan: status=%s', plan.status)
    except PlanExecutionStopped:
        logger.info('Collect plan %s stopped', plan_id)
        try:
            refresh_django_db_connections('before marking plan stopped')
            plan = CollectPlan.objects.get(id=plan_id)
            plan.status = 'STOPPED'
            plan.completed_at = None
            plan.save(update_fields=['status', 'completed_at'])
        except Exception:
            logger.exception('Failed to mark collect plan as stopped')
    except Exception as e:
        logger.exception('Collect plan execution failed: %s', e)
        try:
            refresh_django_db_connections('before marking plan failed')
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
            api_cache_enabled=get_cache_control(job.config, 'api_cache_enabled'),
            api_cache_bypass=get_cache_control(job.config, 'api_cache_bypass'),
            api_cache_ttl_seconds=get_cache_control(job.config, 'api_cache_ttl_seconds'),
        )
        ensure_plan_not_stopped(effective_plan_id)
        job.start()
        logger.info('Starting collect job')
        execute_collect(job)
        refresh_django_db_connections('before marking job success')
        job.complete(success=True, message='执行完成')
        logger.info('Finished collect job: status=SUCCESS')
    except PlanExecutionStopped:
        logger.info('Collect job %s stopped', job_id)
        try:
            refresh_django_db_connections('before marking job stopped')
            job = CollectJob.objects.get(id=job_id)
            job.stop(message='任务已停止')
        except Exception:
            logger.exception('Failed to mark collect job as stopped: job_id=%s', job_id)
    except Exception as e:
        logger.exception('Collect job execution failed: %s', e)
        try:
            refresh_django_db_connections('before marking job failed')
            job = CollectJob.objects.get(id=job_id)
            job.complete(success=False, message=str(e))
        except Exception:
            logger.exception('Failed to mark collect job as failed: job_id=%s', job_id)
    finally:
        if 'context_token' in locals():
            reset_collect_execution_context(context_token)


def refresh_django_db_connections(reason):
    logger.debug('Refreshing Django database connections: %s', reason)
    db.connections.close_all()


def execute_collect(job):
    from saa_collector.services.factory.compound_service_factory import CompoundServiceFactory

    factory = CompoundServiceFactory()
    data_type = job.data_type
    symbols = job.config.get('symbols') if job.config.get('symbols') else None
    params = normalize_schedule_params(job.config.get('params', {}))
    start_value = job.config.get('start_date')
    end_value = job.config.get('end_date')
    if start_value not in (None, ''):
        params = dict(params, start_date=start_value)
    if end_value not in (None, ''):
        params = dict(params, end_date=end_value)
    calendar_service = None

    def refresh_trade_calendar(latest_trade_day, base_date):
        nonlocal calendar_service
        if latest_trade_day is None or base_date is None:
            return
        if calendar_service is None:
            calendar_service = factory.create_calendar_service()

        refresh_start = latest_trade_day + timedelta(days=1)
        if refresh_start > base_date:
            return
        calendar_service.collect(refresh_start, base_date)

    start_date, end_date, params = resolve_schedule_date_range(
        params,
        today=timezone.localdate(),
        trade_calendar_refresher=refresh_trade_calendar,
    )

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
            symbols = build_symbols_for_service(service, symbols)
            symbols = filter_existing_symbols_for_job(job, symbols, start_date, end_date)
            if not symbols:
                return
            execute_resumable_symbol_loop(
                job,
                symbols,
                lambda symbol: service.collect([symbol], progress_enabled=False),
            )
        elif data_type == 'securities':
            from saa_collector.services.common.security_master_service import SecurityMasterRefreshService
            SecurityMasterRefreshService().refresh_from_stocks()
        elif data_type == 'quote':
            service = factory.create_quote_service()
            symbols = build_symbols_for_service(service, symbols)
            symbols = filter_existing_symbols_for_job(job, symbols, start_date, end_date)
            if not symbols:
                return
            service.collect(symbols)
        elif data_type == 'historical_quote':
            service = factory.create_quote_service()
            symbols = build_symbols_for_service(service, symbols)
            symbols = filter_existing_symbols_for_job(job, symbols, start_date, end_date)
            if not symbols:
                return
            service.collect_historical(symbols, start_date=start_date, end_date=end_date)
        elif data_type == 'extras':
            from saa_collector.services.common.stock_status_service import StockStatusService
            if should_skip_existing_job(job) and stock_status_target_date_is_complete(end_date or start_date):
                record_skip_existing_summary(job.id, None, 0, 0, 'target-date-complete')
                logger.info(
                    'Skipping extras collect: target date already complete date=%s',
                    end_date or start_date,
                )
                return
            service = StockStatusService()
            service.collect(end_date or start_date)
        elif data_type == 'index_quotes':
            from saa_collector.services.common.index_quote_service import IndexQuoteService
            service = IndexQuoteService()
            service.collect(symbols, start_date, end_date)
        elif data_type == 'index_weights':
            from saa_collector.services.common.index_weight_service import IndexWeightService
            service = IndexWeightService()
            service.collect(symbols, start_date, end_date)
        elif data_type == 'industries':
            from saa_collector.services.common.sw_industry_service import SwIndustryService
            service = SwIndustryService()
            service.collect_industries(end_date or start_date)
        elif data_type == 'industry_stocks':
            from saa_collector.services.common.sw_industry_service import SwIndustryService
            service = SwIndustryService()
            service.collect_industry_stocks(symbols, end_date or start_date)
        elif data_type == 'financial_statements':
            service = factory.create_statement_service()
            symbols = apply_data_type_symbol_scope(data_type, service, symbols)
            symbols = filter_existing_symbols_for_job(job, symbols, start_date, end_date)
            if not symbols:
                return
            remaining_symbols = initialize_symbol_progress(job.id, symbols)
            if not remaining_symbols:
                logger.info('Skipping financial statements collect: all %d symbols completed', len(symbols))
                clear_symbol_progress(job.id)
                return

            failed_symbols = []

            def on_symbol_success(symbol):
                mark_symbol_success(job.id, symbol)
                ensure_plan_not_stopped(job.plan_id)

            def on_symbol_failure(symbol):
                failed_symbols.append(symbol)
                mark_symbol_failure(job.id, symbol)
                ensure_plan_not_stopped(job.plan_id)

            service.produce(
                remaining_symbols,
                start_date,
                on_symbol_success=on_symbol_success,
                on_symbol_failure=on_symbol_failure,
                after_symbol=release_process_memory,
                progress_total_symbols=len(symbols),
                progress_completed_symbols=len(symbols) - len(remaining_symbols),
                )
            if failed_symbols:
                raise RuntimeError(
                    'financial_statements failed for {} symbols: {}'.format(
                        len(failed_symbols), ','.join(failed_symbols[:20])
                    )
                )
        elif data_type in ('balance_sheet', 'income', 'cash_flow', 'dividend'):
            service = factory.create_statement_service()
            symbols = apply_data_type_symbol_scope(data_type, service, symbols)
            symbols = filter_existing_symbols_for_job(job, symbols, start_date, end_date)
            if not symbols:
                return
            report_types = params.get('report_types', [])
            if report_types:
                logger.info(
                    'Running multi-report statement job without generic symbol resume: report_types=%s',
                    report_types
                )
                if 'balance_sheet' in report_types:
                    service.collect_balance_sheet(symbols, start_date)
                if 'income' in report_types:
                    service.collect_income(symbols, start_date)
                if 'cash_flow' in report_types:
                    service.collect_cash_flow(symbols, start_date)
                if 'dividend' in report_types:
                    service.collect_dividend(symbols, start_date)
            elif data_type == 'balance_sheet':
                execute_resumable_symbol_loop(
                    job, symbols,
                    lambda symbol: service.collect_balance_sheet([symbol], start_date, progress_enabled=False),
                    start_date=start_date,
                )
            elif data_type == 'income':
                execute_resumable_symbol_loop(
                    job, symbols,
                    lambda symbol: service.collect_income([symbol], start_date, progress_enabled=False),
                    start_date=start_date,
                )
            elif data_type == 'cash_flow':
                execute_resumable_symbol_loop(
                    job, symbols,
                    lambda symbol: service.collect_cash_flow([symbol], start_date, progress_enabled=False),
                    start_date=start_date,
                )
            elif data_type == 'dividend':
                execute_resumable_symbol_loop(
                    job, symbols,
                    lambda symbol: service.collect_dividend([symbol], start_date, progress_enabled=False),
                    start_date=start_date,
                )
        elif data_type == 'capital':
            service = factory.create_capital_service()
            symbols = apply_data_type_symbol_scope(data_type, service, symbols)
            symbols = filter_existing_symbols_for_job(job, symbols, start_date, end_date)
            if not symbols:
                return
            execute_resumable_symbol_loop(
                job,
                symbols,
                lambda symbol: service.collect([symbol], start_date, progress_enabled=False),
                start_date=start_date,
            )
        elif data_type == 'main_business':
            service = factory.create_statement_service()
            symbols = apply_data_type_symbol_scope(data_type, service, symbols)
            symbols = filter_existing_symbols_for_job(job, symbols, start_date, end_date)
            if not symbols:
                return
            execute_resumable_symbol_loop(
                job,
                symbols,
                lambda symbol: service.collect_main_business([symbol], start_date, progress_enabled=False),
                start_date=start_date,
            )
        elif data_type == 'valuation':
            from saa_collector.jobs.valuation_collect_job import ValuationCollectJob
            collect_job = ValuationCollectJob()
            collect_job()
        elif data_type == 'csrc_industry_classifications':
            from saa_collector.services.common.industry_classification_service import CsrcIndustryClassificationService
            service = CsrcIndustryClassificationService()
            service.collect()
        elif data_type == 'tick':
            from saa_collector.jobs.tick_job import TickJob
            collect_job = TickJob()
            collect_job()
        else:
            logger.warning(f"[Job {job.id}] Unknown data type: {data_type}")
    finally:
        reset_collect_execution_context(unit_context_token)


def ensure_plan_not_stopped(plan_id):
    if not plan_id:
        return
    status = (
        CollectPlan.objects
        .filter(id=plan_id)
        .values_list('status', flat=True)
        .first()
    )
    if status == 'STOPPED':
        raise PlanExecutionStopped()


def get_remaining_symbols(job, symbols):
    config = job.config or {}
    if REMAINING_SYMBOLS_KEY in config:
        remaining_symbols = set(config.get(REMAINING_SYMBOLS_KEY) or [])
        return [symbol for symbol in symbols if symbol in remaining_symbols]

    completed_symbols = set(config.get(COMPLETED_SYMBOLS_KEY, []))
    return [symbol for symbol in symbols if symbol not in completed_symbols]


def initialize_symbol_progress(job_id, symbols):
    job = CollectJob.objects.get(id=job_id)
    config = dict(job.config or {})
    remaining_symbols = get_remaining_symbols(job, symbols)

    if REMAINING_SYMBOLS_KEY in config and COMPLETED_SYMBOLS_KEY not in config:
        return remaining_symbols

    config.pop(COMPLETED_SYMBOLS_KEY, None)
    if remaining_symbols:
        config[REMAINING_SYMBOLS_KEY] = remaining_symbols
    else:
        config.pop(REMAINING_SYMBOLS_KEY, None)
    job.config = config
    job.save(update_fields=['config'])
    return remaining_symbols


def apply_data_type_symbol_scope(data_type, service, symbols):
    if isinstance(symbols, str):
        symbols = [symbols]
    if symbols is not None:
        symbols = sorted(symbols)

    config = DATA_TYPE_CONFIG.get(data_type, {})
    if config.get('security_scope') == 'a_stock':
        scoped_symbols = service.filter_a_stock_symbols(symbols)
        if symbols is not None and len(scoped_symbols) != len(symbols):
            logger.info(
                'Applied A-stock symbol scope: data_type=%s requested=%d kept=%d dropped=%d',
                data_type, len(symbols), len(scoped_symbols), len(symbols) - len(scoped_symbols)
            )
        return scoped_symbols

    if symbols is None:
        return service.build_symbols(symbols)
    return symbols


def build_symbols_for_service(service, symbols):
    if isinstance(symbols, str):
        symbols = [symbols]
    if symbols is None:
        return service.build_symbols(symbols)
    return sorted(symbols)


def should_skip_existing_job(job):
    config = job.config or {}
    params = config.get('params') or {}
    return bool(config.get('skip_existing') or params.get('skip_existing'))


def filter_existing_symbols_for_job(job, symbols, start_date, end_date):
    if not should_skip_existing_job(job):
        return symbols
    if not symbols:
        return symbols

    kept_symbols, skipped_count, reason = find_symbols_missing_data(
        job.data_type,
        symbols,
        start_date,
        end_date,
    )
    record_skip_existing_summary(job.id, len(symbols), len(kept_symbols), skipped_count, reason)
    if skipped_count:
        logger.info(
            'Applied skip-existing filter: data_type=%s requested=%d kept=%d skipped=%d reason=%s',
            job.data_type,
            len(symbols),
            len(kept_symbols),
            skipped_count,
            reason,
        )
    if not kept_symbols:
        logger.info(
            'Skipping %s collect: all %d symbols already have target data',
            job.data_type,
            len(symbols),
        )
    return kept_symbols


def record_skip_existing_summary(job_id, requested_count, kept_count, skipped_count, reason):
    job = CollectJob.objects.get(id=job_id)
    config = dict(job.config or {})
    config[SKIP_EXISTING_SUMMARY_KEY] = {
        'requested_symbols': requested_count,
        'kept_symbols': kept_count,
        'skipped_symbols': skipped_count,
        'reason': reason,
        'checked_at': timezone.now().isoformat(),
    }
    job.config = config
    job.save(update_fields=['config'])


def find_symbols_missing_data(data_type, symbols, start_date, end_date):
    config = DATA_TYPE_CONFIG.get(data_type) or {}
    table_name = config.get('table')
    if not table_name:
        return symbols, 0, 'unsupported-data-type'

    stock_column = config.get('stock_column') or 'symbol'
    date_column = config.get('date_column')
    unique_symbols = sorted(unique_list(symbols))
    if not date_column:
        existing_symbols = query_existing_symbols(table_name, stock_column, unique_symbols)
        kept_symbols = [symbol for symbol in unique_symbols if symbol not in existing_symbols]
        return kept_symbols, len(unique_symbols) - len(kept_symbols), 'snapshot-symbol-missing'

    if start_date is None or end_date is None:
        return unique_symbols, 0, 'date-range-required'

    frequency = get_skip_existing_frequency(config)
    expected_periods = generate_skip_existing_periods(start_date, end_date, frequency)
    if not expected_periods:
        return unique_symbols, 0, 'no-expected-periods'

    existing_periods = query_existing_symbol_periods(
        table_name,
        stock_column,
        date_column,
        unique_symbols,
        start_date,
        end_date,
        frequency,
    )
    kept_symbols = [
        symbol for symbol in unique_symbols
        if not expected_periods.issubset(existing_periods.get(symbol, set()))
    ]
    return kept_symbols, len(unique_symbols) - len(kept_symbols), f'{frequency}-period-missing'


def get_skip_existing_frequency(config):
    data_frequency = config.get('data_frequency')
    if data_frequency in ('yearly', 'quarterly', 'monthly', 'weekly', 'daily'):
        return data_frequency
    return 'monthly'


def generate_skip_existing_periods(start_date, end_date, frequency):
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        return set()

    periods = set()
    if frequency == 'yearly':
        for year in range(start_date.year, end_date.year + 1):
            periods.add(str(year))
    elif frequency == 'quarterly':
        year = start_date.year
        quarter = (start_date.month - 1) // 3 + 1
        while True:
            period_start = date(year, (quarter - 1) * 3 + 1, 1)
            if period_start > end_date:
                break
            periods.add(f'{year}-Q{quarter}')
            quarter += 1
            if quarter > 4:
                quarter = 1
                year += 1
    elif frequency == 'monthly':
        year = start_date.year
        month = start_date.month
        while True:
            period_start = date(year, month, 1)
            if period_start > end_date:
                break
            periods.add(f'{year}-{month:02d}')
            month += 1
            if month > 12:
                month = 1
                year += 1
    elif frequency == 'daily':
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT date FROM saa_trade_days
                WHERE date BETWEEN %s AND %s
                """,
                [start_date, end_date],
            )
            periods = {str(row[0]) for row in cursor.fetchall()}
    else:
        current = start_date
        while current <= end_date:
            periods.add(current.isoformat())
            current += timedelta(days=1)
    return periods


def query_existing_symbols(table_name, stock_column, symbols):
    if not symbols:
        return set()
    placeholders = ','.join(['%s'] * len(symbols))
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT DISTINCT {stock_column}
            FROM {table_name}
            WHERE {stock_column} IN ({placeholders})
            """,
            symbols,
        )
        return {row[0] for row in cursor.fetchall()}


def query_existing_symbol_periods(table_name, stock_column, date_column, symbols, start_date, end_date, frequency):
    if not symbols:
        return {}

    if frequency == 'yearly':
        select_expr = f"YEAR({date_column})"
    elif frequency == 'quarterly':
        select_expr = f"CONCAT(YEAR({date_column}), '-Q', QUARTER({date_column}))"
    elif frequency == 'monthly':
        select_expr = f"DATE_FORMAT({date_column}, '%Y-%m')"
    else:
        select_expr = date_column

    result = {}
    batch_size = 500
    for index in range(0, len(symbols), batch_size):
        batch = symbols[index:index + batch_size]
        placeholders = ','.join(['%s'] * len(batch))
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT DISTINCT {stock_column}, {select_expr} AS period
                FROM {table_name}
                WHERE {stock_column} IN ({placeholders})
                  AND {date_column} BETWEEN %s AND %s
                """,
                list(batch) + [start_date, end_date],
            )
            for symbol, period in cursor.fetchall():
                result.setdefault(symbol, set()).add(str(period))
    return result


def stock_status_target_date_is_complete(target_date):
    if target_date is None:
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(DISTINCT symbol)
            FROM saa_stocks
            WHERE type = 'STOCK'
              AND market = 'A'
              AND symbol IS NOT NULL
            """
        )
        expected = cursor.fetchone()[0] or 0
        if expected == 0:
            return False
        cursor.execute(
            """
            SELECT COUNT(DISTINCT code)
            FROM saa_extras
            WHERE date = %s
            """,
            [target_date],
        )
        actual = cursor.fetchone()[0] or 0
        return actual >= expected


def execute_resumable_symbol_loop(job, symbols, collect_symbol, label=None, start_date=None):
    data_type_label = label or job.data_type
    remaining_symbols = initialize_symbol_progress(job.id, symbols)
    if not remaining_symbols:
        logger.info('Skipping %s collect: all %d symbols completed', data_type_label, len(symbols))
        clear_symbol_progress(job.id)
        return

    failed_symbols = []
    progress = ProgressLogger.for_symbols(
        logger,
        remaining_symbols,
        profile=get_progress_profile(data_type_label),
        start_date=start_date,
        display_completed_items=len(symbols) - len(remaining_symbols),
        display_total_items=len(symbols),
    )
    for symbol in remaining_symbols:
        try:
            ensure_plan_not_stopped(job.plan_id)
            collect_symbol(symbol)
        except PlanExecutionStopped:
            raise
        except Exception as e:
            logger.exception('Failed to collect %s for symbol %s', data_type_label, symbol)
            failed_symbols.append((symbol, str(e)))
            mark_symbol_failure(job.id, symbol)
            progress.failed('Failed collecting {}'.format(data_type_label), symbol)
        else:
            mark_symbol_success(job.id, symbol)
            progress.finished('Finished collecting {}'.format(data_type_label), symbol)
        finally:
            release_process_memory(symbol)
        ensure_plan_not_stopped(job.plan_id)

    if failed_symbols:
        raise RuntimeError(
            '{} failed for {} symbols: {}'.format(
                data_type_label,
                len(failed_symbols),
                ','.join(format_failed_symbol(symbol, reason) for symbol, reason in failed_symbols[:20])
            )
        )


def get_progress_profile(data_type_label):
    return {
        'balancesheet': 'balance_sheet',
        'balance_sheet': 'balance_sheet',
        'cashflow': 'cash_flow',
        'cash_flow': 'cash_flow',
    }.get(data_type_label, data_type_label)


def format_failed_symbol(symbol, reason):
    if not reason:
        return symbol
    return '{} ({})'.format(symbol, reason[:120])


def mark_symbol_success(job_id, symbol):
    update_symbol_progress(job_id, completed_symbol=symbol)


def mark_symbol_failure(job_id, symbol):
    update_symbol_progress(job_id, failed_symbol=symbol)


def update_symbol_progress(job_id, completed_symbol=None, failed_symbol=None):
    job = CollectJob.objects.get(id=job_id)
    config = dict(job.config or {})
    all_symbols = build_config_symbols(config)
    remaining_symbols = unique_list(config.get(REMAINING_SYMBOLS_KEY, all_symbols))
    failed_symbols = unique_list(config.get(FAILED_SYMBOLS_KEY, []))

    if completed_symbol:
        remaining_symbols = [symbol for symbol in remaining_symbols if symbol != completed_symbol]
        failed_symbols = [symbol for symbol in failed_symbols if symbol != completed_symbol]

    if failed_symbol:
        if failed_symbol not in remaining_symbols:
            remaining_symbols.append(failed_symbol)
        if failed_symbol not in failed_symbols:
            failed_symbols.append(failed_symbol)

    config.pop(COMPLETED_SYMBOLS_KEY, None)
    if remaining_symbols:
        config[REMAINING_SYMBOLS_KEY] = remaining_symbols
    else:
        config.pop(REMAINING_SYMBOLS_KEY, None)

    if failed_symbols:
        config[FAILED_SYMBOLS_KEY] = failed_symbols
    else:
        config.pop(FAILED_SYMBOLS_KEY, None)

    job.config = config
    job.save(update_fields=['config'])


def clear_symbol_progress(job_id):
    job = CollectJob.objects.get(id=job_id)
    config = dict(job.config or {})
    changed = False
    for key in (REMAINING_SYMBOLS_KEY, COMPLETED_SYMBOLS_KEY, FAILED_SYMBOLS_KEY):
        if key in config:
            config.pop(key, None)
            changed = True
    if changed:
        job.config = config
        job.save(update_fields=['config'])


def build_config_symbols(config):
    symbols = (config or {}).get('symbols') or []
    if isinstance(symbols, str):
        symbols = [symbols]
    return sorted(symbols)


def unique_list(values):
    result = []
    for value in values or []:
        if value not in result:
            result.append(value)
    return result


def release_process_memory(symbol=None):
    gc.collect()
    try:
        ctypes.CDLL('libc.so.6').malloc_trim(0)
    except Exception:
        logger.debug('malloc_trim is unavailable', exc_info=True)


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
