"""Stub for homeassistant.components.binary_sensor."""

from enum import StrEnum


class BinarySensorDeviceClass(StrEnum):
    PROBLEM = "problem"


class BinarySensorEntity:
    _attr_is_on = None
    _attr_device_class = None

    @property
    def is_on(self):
        return self._attr_is_on

    @property
    def device_class(self):
        return self._attr_device_class
