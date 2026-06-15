import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from saa_collector.models import ExternalApiCacheEntry


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachedApiResponse:
    body: bytes
    content_type: str = ''
    encoding: str = ''
    filename: str = ''
    status_code: int | None = None
    headers: dict | None = None


class DjangoExternalApiCacheStore:
    def _format_params(self, params):
        if not params:
            return '-'
        parts = []
        for key, value in sorted(params.items()):
            parts.append('{}={}'.format(key, self._format_param_value(value)))
        return ','.join(parts)

    def _format_param_value(self, value):
        if isinstance(value, list):
            if len(value) <= 5:
                return '[' + ','.join(str(item) for item in value) + ']'
            return '[' + ','.join(str(item) for item in value[:5]) + ',...;count={}]'.format(len(value))
        if value is None:
            return 'null'
        return str(value)

    def get_response(self, *, provider, api_name, cache_key):
        now = timezone.now()
        entry = ExternalApiCacheEntry.objects.filter(
            provider=provider,
            api_name=api_name,
            cache_key=cache_key,
        ).first()
        if entry is None:
            logger.info(
                'External API cache miss: provider=%s api=%s params=%s cache_key=%s',
                provider, api_name, '-', cache_key
            )
            return None

        if entry.expires_at <= now:
            logger.info(
                'External API cache expired: provider=%s api=%s params=%s cache_key=%s expires_at=%s',
                provider, api_name, self._format_params(entry.params_json), cache_key, entry.expires_at
            )
            return None

        ExternalApiCacheEntry.objects.filter(pk=entry.pk).update(
            hit_count=entry.hit_count + 1,
            last_hit_at=now,
        )
        logger.info(
            'External API cache hit: provider=%s api=%s params=%s cache_key=%s',
            provider, api_name, self._format_params(entry.params_json), cache_key
        )
        return CachedApiResponse(
            body=bytes(entry.response_body),
            content_type=entry.response_content_type,
            encoding=entry.response_encoding,
            filename=entry.response_filename,
            status_code=entry.response_status_code,
            headers=entry.response_headers_json,
        )

    def set_response(
            self, *, provider, api_name, cache_key, canonical_call, params,
            body, content_type='', filename='', status_code=None, headers=None,
            schema_version, ttl_seconds, fields='', encoding='', request_method='',
            request_url='', request_body=''):
        body = bytes(body or b'')
        expires_at = timezone.now() + timedelta(seconds=ttl_seconds)
        with transaction.atomic():
            ExternalApiCacheEntry.objects.update_or_create(
                cache_key=cache_key,
                defaults={
                    'provider': provider,
                    'api_name': api_name,
                    'canonical_call_json': canonical_call,
                    'params_json': params,
                    'fields': fields or '',
                    'request_method': request_method or '',
                    'request_url': request_url or '',
                    'request_body': request_body or '',
                    'response_status_code': status_code,
                    'response_headers_json': dict(headers or {}),
                    'response_content_type': content_type or '',
                    'response_encoding': encoding or '',
                    'response_filename': filename or '',
                    'response_body': body,
                    'response_sha256': hashlib.sha256(body).hexdigest(),
                    'raw_response_schema_version': schema_version,
                    'expires_at': expires_at,
                },
            )
        logger.info(
            'External API cache stored: provider=%s api=%s params=%s cache_key=%s ttl_seconds=%s bytes=%d',
            provider, api_name, self._format_params(params), cache_key, ttl_seconds, len(body)
        )

    def get_records(self, *, provider, api_name, cache_key):
        cached = self.get_response(provider=provider, api_name=api_name, cache_key=cache_key)
        if cached is None:
            return None
        encoding = cached.encoding or 'utf-8'
        return json.loads(cached.body.decode(encoding))

    def set_records(
            self, *, provider, api_name, cache_key, canonical_call,
            params, fields, response_records, schema_version, ttl_seconds):
        body = json.dumps(
            response_records or [],
            ensure_ascii=False,
            separators=(',', ':'),
        ).encode('utf-8')
        self.set_response(
            provider=provider,
            api_name=api_name,
            cache_key=cache_key,
            canonical_call=canonical_call,
            params=params,
            fields=fields,
            body=body,
            content_type='application/json',
            encoding='utf-8',
            schema_version=schema_version,
            ttl_seconds=ttl_seconds,
        )

    def get(self, *, provider, api_name, cache_key):
        return self.get_records(provider=provider, api_name=api_name, cache_key=cache_key)

    def set(
            self, *, provider, api_name, cache_key, canonical_call,
            params, fields, response_records, schema_version, ttl_seconds):
        self.set_records(
            provider=provider,
            api_name=api_name,
            cache_key=cache_key,
            canonical_call=canonical_call,
            params=params,
            fields=fields,
            response_records=response_records,
            schema_version=schema_version,
            ttl_seconds=ttl_seconds,
        )
