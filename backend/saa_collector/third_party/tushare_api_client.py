# -*- coding: UTF-8 -*-
import logging
import os
import time
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_UP
from urllib.parse import urlparse

import requests
import tushare as ts

try:
    import redis
except ImportError:
    redis = None


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
        self.redis_client = self._build_redis_client()
        self.rate_limit_key = os.getenv('TUSHARE_RATE_LIMIT_KEY', 'saa_collector:tushare:last_query_at')
        self.rate_limit_lock_key = os.getenv('TUSHARE_RATE_LIMIT_LOCK_KEY', 'saa_collector:tushare:rate_limit_lock')
        self._logger.info(
            'TushareApiClient initialized: rate_limit=%s, interval=%.1fs, global_limiter=%s',
            rate_limit, self.interval, bool(self.redis_client)
        )

    def query(self, sub_resource, fields='', **kwargs):
        self._wait_for_rate_limit()
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

    def _build_redis_client(self):
        if redis is None:
            return None

        redis_url = (
            os.getenv('TUSHARE_RATE_LIMIT_REDIS_URL')
            or os.getenv('CELERY_BROKER_URL')
            or os.getenv('CELERY_RESULT_BACKEND')
        )
        if not redis_url or not redis_url.startswith('redis://'):
            return None

        without_scheme = redis_url[len('redis://'):]
        if without_scheme.startswith(':') and without_scheme.count('@') > 1:
            try:
                return self._build_redis_client_from_url(redis_url)
            except Exception as e:
                self._logger.warning('Failed to initialize Redis rate limiter: %s', e)
                return None

        try:
            return redis.Redis.from_url(redis_url, socket_timeout=5, socket_connect_timeout=5)
        except Exception as e:
            self._logger.warning('Failed to initialize Redis rate limiter from URL, retrying manual parse: %s', e)

        try:
            return self._build_redis_client_from_url(redis_url)
        except Exception as e:
            self._logger.warning('Failed to initialize Redis rate limiter: %s', e)
            return None

    def _build_redis_client_from_url(self, redis_url):
        without_scheme = redis_url[len('redis://'):]
        password = None
        if without_scheme.startswith(':') and '@' in without_scheme:
            password, host_and_db = without_scheme[1:].rsplit('@', 1)
        else:
            parsed = urlparse(redis_url)
            password = parsed.password
            host_and_db = parsed.netloc.rsplit('@', 1)[-1] + (parsed.path or '')

        if '/' in host_and_db:
            host_port, db = host_and_db.split('/', 1)
            db = int(db or 0)
        else:
            host_port = host_and_db
            db = 0

        if ':' in host_port:
            host, port = host_port.rsplit(':', 1)
            port = int(port)
        else:
            host = host_port
            port = 6379

        return redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            socket_timeout=5,
            socket_connect_timeout=5,
        )

    def _wait_for_rate_limit(self):
        if self.redis_client:
            try:
                self._wait_for_global_rate_limit()
                return
            except Exception as e:
                self._logger.warning('Redis rate limiter failed, fallback to process-local limiter: %s', e)

        elapsed_seconds = (datetime.now() - self.last_query_time).total_seconds()
        if elapsed_seconds < self.interval:
            time.sleep(self.interval - elapsed_seconds)

    def _wait_for_global_rate_limit(self):
        lock_token = str(uuid.uuid4())
        while not self.redis_client.set(self.rate_limit_lock_key, lock_token, nx=True, px=30000):
            time.sleep(0.1)

        try:
            now = time.time()
            raw_last_query_at = self.redis_client.get(self.rate_limit_key)
            if raw_last_query_at:
                elapsed_seconds = now - float(raw_last_query_at)
                if elapsed_seconds < self.interval:
                    wait_seconds = self.interval - elapsed_seconds
                    self._logger.debug('Tushare global rate limit sleep %.2fs', wait_seconds)
                    time.sleep(wait_seconds)

            self.redis_client.set(self.rate_limit_key, str(time.time()), ex=3600)
        finally:
            current_token = self.redis_client.get(self.rate_limit_lock_key)
            if current_token and current_token.decode() == lock_token:
                self.redis_client.delete(self.rate_limit_lock_key)

    def __getattr__(self, name):
        """Delegate undefined attribute access to the underlying tushare DataApi."""
        return getattr(self.pro, name)


_client = None


def get_tushare_client(token=None, rate_limit=None):
    global _client
    if _client is None:
        if token is None:
            raise ValueError("token is required for first initialization")
        _client = TushareApiClient(token, rate_limit=rate_limit)
    return _client


if __name__ == "__main__":
    pass
