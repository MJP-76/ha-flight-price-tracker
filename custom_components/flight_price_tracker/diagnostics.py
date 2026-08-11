"""Diagnostics support for Flight Price Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from .const import CONF_PROVIDER, CONF_SCAN_INTERVAL_HOURS, CONF_TRIPS, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    return {
        "entry": {
            "provider": entry.data.get(CONF_PROVIDER),
            "api_key_set": bool(entry.data.get(CONF_API_KEY)),
            "scan_interval_hours": entry.options.get(CONF_SCAN_INTERVAL_HOURS),
            "trip_count": len(entry.options.get(CONF_TRIPS, [])),
        },
        "trips": coordinator.data,
    }
