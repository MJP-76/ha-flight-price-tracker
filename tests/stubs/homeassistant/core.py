"""Core stubs used by the integration at import time."""

from enum import IntEnum


class SupportsResponse(IntEnum):
    NONE = 0
    OPTIONAL = 1
    REQUIRED = 2


class HomeAssistant:
    """Stub; only type annotations reference this."""

    data = None


class ServiceCall:
    def __init__(self, domain, service, data, context=None):
        self.domain = domain
        self.service = service
        self.data = data or {}
        self.context = context


def callback(func):
    return func
