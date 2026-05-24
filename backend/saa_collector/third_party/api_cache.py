import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from saa_collector.models import ExternalApiCacheEntry


logger = logging.getLogger(__name__)


class DjangoExternalApiCacheStore:
    def get(self, *, provider, api_name, cache_key):
        now = timezone.now()
        entry = ExternalApiCacheEntry.objects.filter(
            provider=provider,
            api_name=api_name,
            cache_key=cache_key,
        ).first()
        if entry is None:
            logger.info(
                'External API cache miss: provider=%s api=%s cache_key=%s',
                provider, api_name, cache_key
            )
            return None

        if entry.expires_at <= now:
            logger.info(
                'External API cache expired: provider=%s api=%s cache_key=%s expires_at=%s',
                provider, api_name, cache_key, entry.expires_at
            )
            return None

        ExternalApiCacheEntry.objects.filter(pk=entry.pk).update(
            hit_count=entry.hit_count + 1,
            last_hit_at=now,
        )
        logger.info(
            'External API cache hit: provider=%s api=%s cache_key=%s',
            provider, api_name, cache_key
        )
        return entry.response_json

    def set(
            self, *, provider, api_name, cache_key, canonical_call,
            params, fields, response_records, schema_version, ttl_seconds):
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
                    'response_json': response_records,
                    'raw_response_schema_version': schema_version,
                    'expires_at': expires_at,
                },
            )
        logger.info(
            'External API cache stored: provider=%s api=%s cache_key=%s ttl_seconds=%s records=%d',
            provider, api_name, cache_key, ttl_seconds, len(response_records or [])
        )
