# -*- coding: UTF-8 -*-
import logging
import time
from datetime import datetime
from decimal import Decimal, ROUND_UP

import requests
import tushare as ts


class TushareApiException(Exception):
    pass


class TushareApiClient:
    DEFAULT_REQUEST_PER_MINUTES = 80
    MAX_RETRIES = 3
    RETRY_BACKOFF_FACTOR = 5  # seconds, multiplied by 2^attempt

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
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                self._logger.info(
                    'Start to call pro.query(%s, %s, %s)%s',
                    sub_resource, fields[:20],
                    ', '.join(['{}={!r}'.format(k, v) for k, v in kwargs.items()]),
                    f' (retry {attempt}/{self.MAX_RETRIES})' if attempt > 0 else ''
                )
                result = self.pro.query(sub_resource, fields, **kwargs)
                self._logger.info(
                    'End up calling pro.query(%s, ..., ...) with %d records return',
                    sub_resource, len(result.index)
                )
                return result
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    wait = self.RETRY_BACKOFF_FACTOR * (2 ** attempt)
                    self._logger.warning(
                        '[Retry %d/%d] Connection error for %s: %s, waiting %ds before retry',
                        attempt + 1, self.MAX_RETRIES, sub_resource, e, wait
                    )
                    time.sleep(wait)
                else:
                    self._logger.error(
                        '[Retry exhausted] %s failed after %d attempts: %s',
                        sub_resource, self.MAX_RETRIES, e
                    )
            except Exception as e:
                self._logger.error('API error for %s: %s', sub_resource, e)
                raise TushareApiException(str(e)) from e
            finally:
                self.last_query_time = datetime.now()
        raise TushareApiException(
            f'{sub_resource} failed after {self.MAX_RETRIES} retries: {last_error}'
        ) from last_error


if __name__ == "__main__":
    pass
