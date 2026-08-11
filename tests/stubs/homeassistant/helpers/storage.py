"""Stub for homeassistant.helpers.storage."""


class Store:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, version, key, private=False):
        self.hass = hass
        self.version = version
        self.key = key
        self.private = private
        self._data = None

    async def async_load(self):
        return self._data

    async def async_save(self, data):
        self._data = data
