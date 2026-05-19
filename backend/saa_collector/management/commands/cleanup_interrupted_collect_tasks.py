from django.core.management.base import BaseCommand
from django.utils import timezone

from saa_collector.models import CollectJob, CollectPlan


class Command(BaseCommand):
    help = 'Mark interrupted running collect plans and jobs as failed.'

    def handle(self, *args, **options):
        now = timezone.now()
        plans = CollectPlan.objects.filter(status='RUNNING').update(
            status='FAILED',
            completed_at=now,
        )
        jobs = CollectJob.objects.filter(status='RUNNING').update(
            status='FAILED',
            end_time=now,
            message='服务重启，任务中断',
        )
        self.stdout.write(self.style.SUCCESS(
            f'Marked {plans} running collect plans and {jobs} running collect jobs as failed.'
        ))
