import logging.config
import logging.handlers
import os


class LoggingInitializer:
    def __init__(self):
        pass

    @staticmethod
    def init():
        if os.name == 'nt':
            path = os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
        else:
            path = '/var/log/saa_collector'
        logging.config.fileConfig(
            os.path.join(os.path.expanduser('~'), '.saa_collector', 'config', 'logging.conf'),
            defaults={
                'log_file_name': os.path.join(path, 'saa_collector.log')
            }
        )
