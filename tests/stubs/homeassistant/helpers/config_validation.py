"""Stub for homeassistant.helpers.config_validation (cv)."""


def date(value):
    return value


def boolean(value):
    return value


def positive_float(value):
    return float(value)


def ensure_list(value):
    if isinstance(value, list):
        return value
    return [value]
