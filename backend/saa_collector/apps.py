from django.apps import AppConfig
import os


class SaaCollectorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'saa_collector'
    verbose_name = '数据采集'

    def ready(self):
        self._cleanup_stale_running_status()

        if os.environ.get('RUN_SCHEDULER') == 'true':
            import sys
            # 避免在 runserver 的 auto-reloader 子进程中重复启动 scheduler
            if os.environ.get('RUN_MAIN') == 'true' or 'runserver' not in sys.argv:
                from .scheduler_manager import init_scheduler
                init_scheduler()

    def _cleanup_stale_running_status(self):
        import sys

        if 'collectstatic' in sys.argv:
            return

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
