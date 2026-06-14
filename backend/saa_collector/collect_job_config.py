API_CACHE_CONTROL_KEYS = (
    'api_cache_enabled',
    'api_cache_bypass',
    'api_cache_ttl_seconds',
)

from saa_collector.date_expressions import normalize_schedule_params
from saa_collector.constants import DATA_TYPE_CONFIG


def build_collect_job_config(symbols=None, params=None, data_type=None, **extra):
    params = normalize_schedule_params(params)
    config = {
        'symbols': symbols or [],
        'params': params,
        'api_cache_enabled': params.get('api_cache_enabled', True),
    }

    for key in ('api_cache_bypass', 'api_cache_ttl_seconds'):
        if key in params:
            config[key] = params[key]

    date_anchor = extra.pop('date_anchor', None)
    if date_anchor is None:
        date_anchor = params.get('date_anchor')
    if date_anchor is None and data_type:
        date_anchor = (DATA_TYPE_CONFIG.get(data_type) or {}).get('date_anchor')
    if date_anchor is not None:
        config['date_anchor'] = date_anchor

    for key, value in extra.items():
        if value is not None:
            config[key] = value

    return config


def get_cache_control(config, key, default=None):
    config = config or {}
    params = config.get('params') or {}
    if key in config:
        return config.get(key)
    return params.get(key, default)
