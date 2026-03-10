from .base import *

DEBUG = True

DATABASES['default']['NAME'] = 'saa'

LOGGING['loggers']['django']['level'] = 'DEBUG'
LOGGING['loggers']['saa_collector']['level'] = 'DEBUG'
LOGGING['loggers']['django.utils.autoreload'] = {'level': 'WARNING'}
