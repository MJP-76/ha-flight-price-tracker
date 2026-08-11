"""Stub for homeassistant.components.sensor."""

from enum import StrEnum


class SensorDeviceClass(StrEnum):
    MONETARY = "monetary"
    DURATION = "duration"
    TIMESTAMP = "timestamp"


class SensorStateClass(StrEnum):
    MEASUREMENT = "measurement"
    TOTAL = "total"


class SensorEntity:
    _attr_device_class = None
    _attr_state_class = None
    _attr_unit_of_measurement = None
    _attr_native_value = None

    @property
    def device_class(self):
        return self._attr_device_class

    @property
    def state_class(self):
        return self._attr_state_class

    @property
    def unit_of_measurement(self):
        return self._attr_unit_of_measurement

    @property
    def native_value(self):
        return self._attr_native_value
