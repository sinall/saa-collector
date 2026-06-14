import logging

from celery import current_app
from django.db import transaction
from django.utils import timezone

from saa_collector.collect_job_config import build_collect_job_config
from saa_collector.models import CollectJob, CollectPlan

logger = logging.getLogger(__name__)


PROGRESS_KEYS = ('remaining_symbols', 'completed_symbols', 'failed_symbols')


def dispatch_plan(plan, jobs_queryset=None):
    plan.status = 'QUEUED'
    plan.started_at = None
    plan.completed_at = None
    plan.queued_at = timezone.now()
    plan.queue_task_id = None
    plan.save(update_fields=['status', 'started_at', 'completed_at', 'queued_at', 'queue_task_id'])
    if jobs_queryset is None:
        jobs_queryset = plan.jobs.all()
    jobs_queryset.update(status='QUEUED', start_time=None, end_time=None, message=None)

    from saa_collector.tasks import execute_collect_plan
    async_result = execute_collect_plan.delay(plan.id)

    plan.queue_task_id = async_result.id
    plan.save(update_fields=['queue_task_id'])
    logger.info(f"Queued collect plan {plan.id} as celery task {async_result.id}")
    return async_result.id


def reset_plan_for_dispatch(plan):
    if plan.status in ('COMPLETED', 'FAILED', 'STOPPED'):
        plan.status = 'PENDING'
        plan.started_at = None
        plan.completed_at = None
        plan.queued_at = None
        plan.queue_task_id = None
        plan.save(update_fields=['status', 'started_at', 'completed_at', 'queued_at', 'queue_task_id'])
        for job in plan.jobs.all():
            config = dict(job.config or {})
            changed = False
            for key in PROGRESS_KEYS:
                if key in config:
                    config.pop(key, None)
                    changed = True
            job.status = 'PENDING'
            job.start_time = None
            job.end_time = None
            job.message = None
            if changed:
                job.config = config
                job.save(update_fields=['status', 'start_time', 'end_time', 'message', 'config'])
            else:
                job.save(update_fields=['status', 'start_time', 'end_time', 'message'])


def stop_plan_execution(plan):
    with transaction.atomic():
        plan = CollectPlan.objects.select_for_update().get(id=plan.id)
        if plan.status not in ('QUEUED', 'RUNNING'):
            raise ValueError('只能停止排队中或执行中的计划')

        if plan.queue_task_id:
            current_app.control.revoke(plan.queue_task_id, terminate=False)

        stopped_at = timezone.now()
        plan.status = 'STOPPED'
        plan.queue_task_id = None
        plan.completed_at = None
        plan.save(update_fields=['status', 'queue_task_id', 'completed_at'])

        plan.jobs.filter(status__in=('QUEUED', 'PENDING', 'RUNNING')).update(
            status='STOPPED',
            end_time=stopped_at,
        )

    logger.info('Stopped collect plan %s', plan.id)
    return plan


def create_plan_from_schedule(schedule, trigger_type):
    triggered_at = schedule.last_triggered_at or timezone.now()
    triggered_at_local = timezone.localtime(triggered_at)
    plan = CollectPlan.objects.create(
        name=f'{schedule.name} - {triggered_at_local:%Y-%m-%d %H:%M}',
        source='SCHEDULE',
        trigger_type=trigger_type,
        source_schedule_id=schedule.id,
        source_schedule_name=schedule.name,
        execution_mode='PARALLEL'
    )

    CollectJob.objects.create(
        plan=plan,
        data_type=schedule.data_type,
        config=build_collect_job_config(
            symbols=schedule.symbols,
            params=schedule.params,
            data_type=schedule.data_type,
        )
    )
    return plan
