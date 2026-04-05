from .base import *

DEBUG = True

LOGGING['loggers']['django']['level'] = 'DEBUG'
LOGGING['loggers']['saa_collector']['level'] = 'DEBUG'
LOGGING['loggers']['django.utils.autoreload'] = {'level': 'WARNING'}
