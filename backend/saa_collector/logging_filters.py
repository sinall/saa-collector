import logging

from saa_collector.services.collect_execution_context import format_collect_log_context


class CollectExecutionContextFilter(logging.Filter):
    def filter(self, record):
        record.collect_context = format_collect_log_context()
        return True
