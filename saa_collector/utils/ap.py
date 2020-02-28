# -*- coding: utf-8 -*-

from apscheduler.triggers.cron import CronTrigger


class APCronParser(object):
    @classmethod
    def parse(cls, expression):
        trigger = CronTrigger.from_crontab(expression)
        return trigger
