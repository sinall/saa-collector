# -*- coding: utf-8 -*-
import logging

from saa_collector.jobs.basic_job import BasicJob


class TickJob(BasicJob):
    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger()

    def __call__(self):
        self._logger.debug("Tick!")
