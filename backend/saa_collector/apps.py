from django.apps import AppConfig
import os


class SaaCollectorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'saa_collector'
    verbose_name = '数据采集'

    def ready(self):
        if os.environ.get('RUN_SCHEDULER') == 'true':
            from .scheduler_manager import init_scheduler
            init_scheduler()
