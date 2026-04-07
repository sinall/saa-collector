from django.apps import AppConfig
import os


class SaaCollectorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'saa_collector'
    verbose_name = '数据采集'

    def ready(self):
        self._cleanup_stale_running_status()

        if os.environ.get('RUN_SCHEDULER') == 'true':
            from .scheduler_manager import init_scheduler
            init_scheduler()

    def _cleanup_stale_running_status(self):
        from django.utils import timezone
        from .models import CollectPlan, CollectJob

        CollectPlan.objects.filter(status='RUNNING').update(
            status='FAILED',
            completed_at=timezone.now(),
        )
        CollectJob.objects.filter(status='RUNNING').update(
            status='FAILED',
            end_time=timezone.now(),
            message='服务重启，任务中断',
        )
