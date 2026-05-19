import logging

from celery import shared_task
from croniter import croniter
from django.db import transaction
from django.utils import timezone

from saa_collector.services.collect_plan_executor import execute_plan

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='saa_collector.execute_collect_plan')
def execute_collect_plan(self, plan_id):
    task_id = getattr(self.request, 'id', None)
    logger.info('Starting collect plan task: task_id=%s plan_id=%s', task_id, plan_id)
    execute_plan(plan_id, task_id=task_id)
    logger.info('Finished collect plan task: task_id=%s plan_id=%s', task_id, plan_id)
    return {'plan_id': plan_id, 'task_id': task_id}


@shared_task(name='saa_collector.scan_due_collect_schedules')
def scan_due_collect_schedules():
    from saa_collector.models import CollectSchedule
    from saa_collector.task_dispatcher import create_plan_from_schedule, dispatch_plan

    now = timezone.now()
    initialized = 0
    created = 0
    dispatched_plan_ids = []

    schedule_ids = list(
        CollectSchedule.objects
        .filter(status='ENABLED')
        .order_by('id')
        .values_list('id', flat=True)
    )

    for schedule_id in schedule_ids:
        plan = None
        with transaction.atomic():
            schedule = (
                CollectSchedule.objects
                .select_for_update()
                .get(id=schedule_id)
            )
            if schedule.status != 'ENABLED':
                continue

            if schedule.next_trigger_at is None:
                schedule.next_trigger_at = get_next_schedule_fire_time(schedule, now)
                schedule.save(update_fields=['next_trigger_at'])
                initialized += 1
                continue

            if schedule.next_trigger_at > now:
                continue

            due_at = schedule.next_trigger_at
            schedule.last_triggered_at = due_at
            schedule.next_trigger_at = get_next_schedule_fire_time(schedule, due_at)
            schedule.save(update_fields=['last_triggered_at', 'next_trigger_at'])

            plan = create_plan_from_schedule(schedule, trigger_type='AUTO')
            created += 1

        if plan is not None:
            dispatch_plan(plan)
            dispatched_plan_ids.append(plan.id)
            logger.info(
                'Created collect plan %s from due schedule %s',
                plan.id, schedule_id
            )

    return {
        'checked': len(schedule_ids),
        'initialized': initialized,
        'created': created,
        'dispatched_plan_ids': dispatched_plan_ids,
    }


def get_next_schedule_fire_time(schedule, previous_fire_time):
    previous_fire_time = timezone.localtime(previous_fire_time)
    return croniter(schedule.cron_expression, previous_fire_time).get_next(timezone.datetime)
