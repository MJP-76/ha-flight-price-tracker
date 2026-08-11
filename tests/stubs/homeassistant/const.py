"""Constants used by the integration at import time."""

from enum import Enum


class Platform(Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


SOURCE_REAUTH = "reauth"
CONF_API_KEY = "api_key"
CONF_CURRENCY = "currency"
