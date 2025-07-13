"""
PyTest Fixtures.
"""

import pytest
from cement import fs

from saa_collector.utils.log import LoggingInitializer


@pytest.fixture(scope="function", autouse=True)
def tmp(request):
    LoggingInitializer.init()
    yield
