import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

VERSION_KEY = 'collector:heatmap:version'
DEFAULT_VERSION = 1


def get_heatmap_cache_version():
    version = cache.get(VERSION_KEY)
    if version is None:
        cache.set(VERSION_KEY, DEFAULT_VERSION, timeout=None)
        return DEFAULT_VERSION
    return version


def build_heatmap_cache_keys(frequency, scope_key, today):
    version = get_heatmap_cache_version()
    prefix = f"collector:heatmap:v{version}:{frequency}:{scope_key}"
    return f"{prefix}:{today}", f"{prefix}:latest"


def invalidate_heatmap_cache():
    try:
        cache.add(VERSION_KEY, DEFAULT_VERSION, timeout=None)
        cache.incr(VERSION_KEY)
        logger.info('heatmap cache invalidated')
    except Exception:
        logger.exception('Failed to invalidate heatmap cache')
