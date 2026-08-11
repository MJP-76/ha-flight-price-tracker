"""Flight Price Tracker integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_PROVIDER,
    DEFAULT_PROVIDER,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import FlightPriceCoordinator
from .providers import ProviderError, get_provider
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Flight Price Tracker from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    try:
        provider = get_provider(
            entry.data.get(CONF_PROVIDER, DEFAULT_PROVIDER),
            hass,
            entry.data.get(CONF_API_KEY, ""),
            base_url=entry.data.get(CONF_BASE_URL) or None,
        )
    except ProviderError as err:
        raise ConfigEntryNotReady(f"Failed to create provider: {err}") from err

    coordinator = FlightPriceCoordinator(hass, entry, provider)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "provider": provider,
    }

    await async_setup_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    if coordinator.auth_failed:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_REAUTH}, data=entry.data
            )
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    await async_unload_services(hass, entry)
    return unload_ok


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry whenever options or data change."""
    await hass.config_entries.async_reload(entry.entry_id)
