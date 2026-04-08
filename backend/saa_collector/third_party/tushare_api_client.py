# -*- coding: UTF-8 -*-
import logging
import time
from datetime import datetime
from decimal import Decimal, ROUND_UP

import tushare as ts


class TushareApiException(Exception):
    pass


class TushareApiClient:
    DEFAULT_REQUEST_PER_MINUTES = 80

    def __init__(self, token, rate_limit=None):
        self._logger = logging.getLogger()
        self.pro = ts.pro_api(token)
        requests_per_minute = rate_limit or self.DEFAULT_REQUEST_PER_MINUTES
        self.interval = float(Decimal(60 / requests_per_minute).quantize(Decimal('.1'), rounding=ROUND_UP))
        self.last_query_time = datetime.now()
        self._logger.info(
            'TushareApiClient initialized: rate_limit=%s, interval=%.1fs',
            rate_limit, self.interval
        )

    def query(self, sub_resource, fields='', **kwargs):
        elapsed_seconds = (datetime.now() - self.last_query_time).total_seconds()
        if elapsed_seconds < self.interval:
            time.sleep(self.interval - elapsed_seconds)
        try:
            self._logger.info(
                'Start to call pro.query(%s, %s, %s)',
                sub_resource, fields[:20], ', '.join(['{}={!r}'.format(k, v) for k, v in kwargs.items()])
            )
            result = self.pro.query(sub_resource, fields, **kwargs)
            self._logger.info(
                'End up calling pro.query(%s, ..., ...) with %d records return',
                sub_resource, len(result.index)
            )
            return result
        finally:
            self.last_query_time = datetime.now()


if __name__ == "__main__":
    pass
