import logging

from django.utils import timezone

from saa_collector.models import CollectJob, CollectPlan

logger = logging.getLogger(__name__)


def dispatch_plan(plan):
    plan.status = 'QUEUED'
    plan.started_at = None
    plan.completed_at = None
    plan.queued_at = timezone.now()
    plan.queue_task_id = None
    plan.save(update_fields=['status', 'started_at', 'completed_at', 'queued_at', 'queue_task_id'])
    plan.jobs.update(status='QUEUED', start_time=None, end_time=None, message=None)

    from saa_collector.tasks import execute_collect_plan
    async_result = execute_collect_plan.delay(plan.id)

    plan.queue_task_id = async_result.id
    plan.save(update_fields=['queue_task_id'])
    logger.info(f"Queued collect plan {plan.id} as celery task {async_result.id}")
    return async_result.id


def reset_plan_for_dispatch(plan):
    if plan.status in ('COMPLETED', 'FAILED'):
        plan.status = 'PENDING'
        plan.started_at = None
        plan.completed_at = None
        plan.queued_at = None
        plan.queue_task_id = None
        plan.save(update_fields=['status', 'started_at', 'completed_at', 'queued_at', 'queue_task_id'])
        plan.jobs.update(
            status='PENDING',
            start_time=None,
            end_time=None,
            message=None
        )


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
        config={
            'symbols': schedule.symbols,
            'params': schedule.params
        }
    )
    return plan
