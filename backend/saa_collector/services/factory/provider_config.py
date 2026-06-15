# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass

import yaml
from django.conf import settings


CONFIG_PATH = '/etc/saa/collector/backend/saa_collector.yml'
SUPPORTED_PROVIDERS = {'akshare', 'tushare'}


@dataclass(frozen=True)
class ProviderSelection:
    provider: str
    source: str


def resolve_provider(data_type=None, config=None, config_path=None):
    config = load_config(config_path) if config is None else config
    collector_config = (config or {}).get('saa_collector') or {}
    data_providers = collector_config.get('data_providers') or {}

    if data_type and data_type in data_providers:
        return build_selection(data_providers[data_type], 'data_providers.{}'.format(data_type))

    default_provider = collector_config.get('default_provider')
    if default_provider:
        return build_selection(default_provider, 'default_provider')

    return build_selection(getattr(settings, 'DATA_SOURCE', 'tushare'), 'settings.DATA_SOURCE')


def require_provider(data_type, supported_providers, config=None):
    selection = resolve_provider(data_type, config=config)
    supported_providers = {normalize_provider(provider) for provider in supported_providers}
    if selection.provider not in supported_providers:
        raise ValueError(
            'Unsupported collector provider for data_type={}: provider={} supported={}'.format(
                data_type,
                selection.provider,
                ','.join(sorted(supported_providers)),
            )
        )
    return selection


def load_config(config_path=None):
    config_path = config_path or os.getenv('SAA_COLLECTOR_CONFIG_PATH') or CONFIG_PATH
    try:
        with open(config_path, 'r') as handle:
            return yaml.load(handle.read(), Loader=yaml.SafeLoader) or {}
    except FileNotFoundError:
        return {}


def build_selection(provider, source):
    provider = normalize_provider(provider)
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError('Unsupported collector provider: {}'.format(provider))
    return ProviderSelection(provider=provider, source=source)


def normalize_provider(provider):
    return str(provider or '').strip().lower()
