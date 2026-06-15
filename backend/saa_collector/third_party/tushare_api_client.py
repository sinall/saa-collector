# -*- coding: UTF-8 -*-
import logging
import os
import time
import uuid
import hashlib
import json
import math
from datetime import date, datetime
from decimal import Decimal, ROUND_UP
from urllib.parse import urlparse

import pandas as pd
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
    CACHE_PROVIDER = 'tushare'
    CACHE_SCHEMA_VERSION = 'tushare-raw-v1'
    CACHE_TTL_BY_API = {
        'balancesheet': 30 * 24 * 60 * 60,
        'income': 30 * 24 * 60 * 60,
        'cashflow': 30 * 24 * 60 * 60,
        'dividend': 30 * 24 * 60 * 60,
        'fina_mainbz': 30 * 24 * 60 * 60,
        'stk_factor': 30 * 24 * 60 * 60,
        'index_classify': 7 * 24 * 60 * 60,
        'index_daily': 24 * 60 * 60,
        'index_weight': 24 * 60 * 60,
        'index_member_all': 24 * 60 * 60,
        'stock_basic': 7 * 24 * 60 * 60,
    }

    def __init__(self, token, rate_limit=None, cache_store=None):
        self._logger = logging.getLogger()
        self.pro = ts.pro_api(token)
        self.cache_store = cache_store
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
        cache_controls = self._pop_cache_controls(kwargs)
        cache_context = self._build_cache_context(sub_resource, fields, kwargs, cache_controls)
        cached_result = self._get_cached_result(cache_context)
        if cached_result is not None:
            return cached_result

        rate_limit_wait_seconds = self._wait_for_rate_limit()
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                self._logger.info(
                    'Start to call pro.query(%s, %s, %s)%s',
                    sub_resource, fields[:20],
                    ', '.join(['{}={!r}'.format(k, v) for k, v in kwargs.items()]),
                    f' (retry {attempt}/{self.MAX_RETRIES})' if attempt > 0 else ''
                )
                call_started_at = time.monotonic()
                result = self.pro.query(sub_resource, fields, **kwargs)
                call_elapsed_seconds = time.monotonic() - call_started_at
                self._store_cached_result(cache_context, result)
                self._logger.info(
                    'End up calling pro.query(%s, ..., ...) with %d records return; '
                    'api_elapsed_seconds=%.3f rate_limit_wait_seconds=%.3f',
                    sub_resource, len(result.index), call_elapsed_seconds, rate_limit_wait_seconds
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

    def build_cache_key(self, sub_resource, fields='', params=None):
        canonical_call = self.build_canonical_call(sub_resource, params or {})
        canonical_json = json.dumps(
            canonical_call, sort_keys=True, separators=(',', ':'), ensure_ascii=True
        )
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

    def build_canonical_call(self, sub_resource, params):
        return {
            'provider': self.CACHE_PROVIDER,
            'api': sub_resource,
            'params': self._normalize_cache_params(params),
            'version': self.CACHE_SCHEMA_VERSION,
        }

    def _normalize_cache_params(self, params):
        normalized = {}
        for key, value in sorted((params or {}).items()):
            if key == 'fields':
                continue
            normalized[key] = self._normalize_cache_value(value)
        return normalized

    def _normalize_cache_value(self, value):
        if value == '':
            return None
        if isinstance(value, (list, tuple, set)):
            return sorted(self._normalize_cache_value(item) for item in value)
        if hasattr(value, 'strftime'):
            return value.strftime('%Y%m%d')
        return value

    def _pop_cache_controls(self, params):
        return {
            'enabled': params.pop('api_cache_enabled', None),
            'bypass': params.pop('api_cache_bypass', False),
            'ttl_seconds': params.pop('api_cache_ttl_seconds', None),
        }

    def _build_cache_context(self, sub_resource, fields, params, controls):
        effective_controls = self._merge_cache_controls_with_execution_context(controls)
        ttl_seconds = self._get_cache_ttl(sub_resource, effective_controls.get('ttl_seconds'))
        enabled = bool(effective_controls.get('enabled'))
        bypass = bool(effective_controls.get('bypass'))

        if not enabled:
            self._logger.info('External API cache disabled: provider=tushare api=%s', sub_resource)
            return {'enabled': False}
        if bypass:
            self._logger.info('External API cache bypassed: provider=tushare api=%s', sub_resource)
            return {'enabled': False}
        if not ttl_seconds or ttl_seconds <= 0:
            self._logger.info('External API cache disabled by policy: provider=tushare api=%s', sub_resource)
            return {'enabled': False}

        canonical_call = self.build_canonical_call(sub_resource, params)
        cache_key = self.build_cache_key(sub_resource, fields=fields, params=params)
        return {
            'enabled': True,
            'provider': self.CACHE_PROVIDER,
            'api_name': sub_resource,
            'cache_key': cache_key,
            'canonical_call': canonical_call,
            'params': canonical_call['params'],
            'fields': fields or '',
            'ttl_seconds': ttl_seconds,
            'schema_version': self.CACHE_SCHEMA_VERSION,
        }

    def _merge_cache_controls_with_execution_context(self, controls):
        merged = dict(controls)
        try:
            from saa_collector.services.collect_execution_context import get_collect_execution_context
            context = get_collect_execution_context()
        except Exception:
            context = {}

        if merged.get('enabled') is None:
            merged['enabled'] = context.get('api_cache_enabled')
        if not merged.get('bypass'):
            merged['bypass'] = context.get('api_cache_bypass', False)
        if merged.get('ttl_seconds') is None:
            merged['ttl_seconds'] = context.get('api_cache_ttl_seconds')
        return merged

    def _get_cache_ttl(self, sub_resource, ttl_override):
        if ttl_override is not None:
            try:
                return int(ttl_override)
            except (TypeError, ValueError):
                self._logger.warning(
                    'Invalid Tushare API cache ttl override: api=%s ttl=%r',
                    sub_resource, ttl_override
                )
                return None
        return self.CACHE_TTL_BY_API.get(sub_resource)

    def _get_cached_result(self, cache_context):
        if not cache_context.get('enabled'):
            return None
        try:
            cache_store = self._get_cache_store()
            records = cache_store.get(
                provider=cache_context['provider'],
                api_name=cache_context['api_name'],
                cache_key=cache_context['cache_key'],
            )
        except Exception as e:
            self._logger.warning('External API cache read failed: %s', e)
            return None

        if records is None:
            return None

        result = pd.DataFrame.from_records(records)
        fields = self._parse_fields(cache_context.get('fields'))
        if fields and not set(fields).issubset(set(result.columns)):
            self._logger.info(
                'External API cache miss: provider=tushare api=%s params=%s cache_key=%s '
                'reason=missing_fields requested=%s cached=%s',
                cache_context['api_name'],
                self._format_cache_params(cache_context.get('params')),
                cache_context['cache_key'],
                fields,
                list(result.columns),
            )
            return None
        if fields:
            result = result.loc[:, fields]
        return result

    def _store_cached_result(self, cache_context, result):
        if not cache_context.get('enabled'):
            return
        try:
            records = self._sanitize_response_records(result.to_dict('records'))
            self._get_cache_store().set(
                provider=cache_context['provider'],
                api_name=cache_context['api_name'],
                cache_key=cache_context['cache_key'],
                canonical_call=cache_context['canonical_call'],
                params=cache_context['params'],
                fields=cache_context['fields'],
                response_records=records,
                schema_version=cache_context['schema_version'],
                ttl_seconds=cache_context['ttl_seconds'],
            )
        except Exception as e:
            self._logger.warning('External API cache write failed: %s', e)

    def _format_cache_params(self, params):
        if not params:
            return '-'
        parts = []
        for key, value in sorted(params.items()):
            parts.append('{}={}'.format(key, self._format_cache_param_value(value)))
        return ','.join(parts)

    def _format_cache_param_value(self, value):
        if isinstance(value, list):
            if len(value) <= 5:
                return '[' + ','.join(str(item) for item in value) + ']'
            return '[' + ','.join(str(item) for item in value[:5]) + ',...;count={}]'.format(len(value))
        if value is None:
            return 'null'
        return str(value)

    def _sanitize_response_records(self, records):
        return [
            {
                key: self._sanitize_json_value(value)
                for key, value in record.items()
            }
            for record in records or []
        ]

    def _sanitize_json_value(self, value):
        if isinstance(value, dict):
            return {
                key: self._sanitize_json_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._sanitize_json_value(item) for item in value]
        if value is None:
            return None
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return None
            return value
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (pd.Timestamp, datetime, date)):
            if pd.isna(value):
                return None
            return value.isoformat()
        if hasattr(value, 'item'):
            try:
                item = value.item()
            except (TypeError, ValueError):
                item = value
            if item is not value:
                return self._sanitize_json_value(item)
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        return value

    def _get_cache_store(self):
        if self.cache_store is None:
            from saa_collector.third_party.api_cache import DjangoExternalApiCacheStore
            self.cache_store = DjangoExternalApiCacheStore()
        return self.cache_store

    def _parse_fields(self, fields):
        return [field.strip() for field in (fields or '').split(',') if field.strip()]

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
                return self._wait_for_global_rate_limit()
            except Exception as e:
                self._logger.warning('Redis rate limiter failed, fallback to process-local limiter: %s', e)

        elapsed_seconds = (datetime.now() - self.last_query_time).total_seconds()
        if elapsed_seconds < self.interval:
            wait_seconds = self.interval - elapsed_seconds
            self._logger.info(
                'Tushare rate limit wait: limiter=local wait_seconds=%.3f '
                'elapsed_seconds=%.3f interval_seconds=%.3f',
                wait_seconds, elapsed_seconds, self.interval
            )
            time.sleep(wait_seconds)
            return wait_seconds
        return 0.0

    def _wait_for_global_rate_limit(self):
        lock_token = str(uuid.uuid4())
        lock_wait_seconds = 0.0
        while not self.redis_client.set(self.rate_limit_lock_key, lock_token, nx=True, px=30000):
            lock_wait_seconds += 0.1
            time.sleep(0.1)

        try:
            rate_wait_seconds = 0.0
            elapsed_seconds = None
            now = time.time()
            raw_last_query_at = self.redis_client.get(self.rate_limit_key)
            if raw_last_query_at:
                elapsed_seconds = now - float(raw_last_query_at)
                if elapsed_seconds < self.interval:
                    rate_wait_seconds = self.interval - elapsed_seconds
                    self._logger.info(
                        'Tushare rate limit wait: limiter=global wait_seconds=%.3f '
                        'elapsed_seconds=%.3f interval_seconds=%.3f lock_wait_seconds=%.3f',
                        rate_wait_seconds, elapsed_seconds, self.interval, lock_wait_seconds
                    )
                    time.sleep(rate_wait_seconds)

            if lock_wait_seconds and not rate_wait_seconds:
                self._logger.info(
                    'Tushare rate limit wait: limiter=global wait_seconds=0.000 '
                    'elapsed_seconds=%s interval_seconds=%.3f lock_wait_seconds=%.3f',
                    'none' if elapsed_seconds is None else f'{elapsed_seconds:.3f}',
                    self.interval,
                    lock_wait_seconds
                )

            self.redis_client.set(self.rate_limit_key, str(time.time()), ex=3600)
            return lock_wait_seconds + rate_wait_seconds
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
