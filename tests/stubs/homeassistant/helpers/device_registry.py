"""Stub for homeassistant.helpers.device_registry."""


def async_get(hass):
    return _DeviceRegistry()


class _DeviceRegistry:
    async def async_get_device(self, identifiers=None):
        return None

    async def async_get_or_create(self, **kwargs):
        return None
