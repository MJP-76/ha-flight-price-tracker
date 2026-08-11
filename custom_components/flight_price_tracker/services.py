"""Services for the Flight Price Tracker integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_CHEAP_PERCENTILE,
    CONF_CURRENCY,
    CONF_DATE_FROM,
    CONF_DATE_TO,
    CONF_DESTINATION,
    CONF_MAX_STOPS,
    CONF_NOTIFY_ON_CHEAP,
    CONF_NOTIFY_ON_TARGET,
    CONF_ORIGIN,
    CONF_PASSENGERS,
    CONF_PROVIDER,
    CONF_RETURN_FROM,
    CONF_RETURN_TO,
    CONF_TARGET_PRICE,
    CONF_TRIP_NAME,
    CONF_TRIPS,
    DEFAULT_PROVIDER,
    DOMAIN,
    MAX_CHEAP_PERCENTILE,
    MAX_TRIPS,
    MIN_CHEAP_PERCENTILE,
)
from .models import make_trip_id, trip_dict_from_form, validate_trip_form
from .providers import ProviderError, get_provider

SERVICE_REFRESH = "refresh"
SERVICE_ADD_TRIP = "add_trip"
SERVICE_UPDATE_TRIP = "update_trip"
SERVICE_REMOVE_TRIP = "remove_trip"
SERVICE_RESOLVE_LOCATION = "resolve_location"

SERVICES_REGISTERED = "services_registered"

ATTR_ENTRY_ID = "entry_id"
ATTR_TRIP_ID = "trip_id"
ATTR_QUERY = "query"

SERVICE_SCHEMA_REFRESH = vol.Schema({vol.Optional(ATTR_ENTRY_ID): str})
SERVICE_SCHEMA_REMOVE_TRIP = vol.Schema(
    {vol.Optional(ATTR_ENTRY_ID): str, vol.Required(ATTR_TRIP_ID): str}
)
SERVICE_SCHEMA_RESOLVE = vol.Schema(
    {vol.Optional(ATTR_ENTRY_ID): str, vol.Required(ATTR_QUERY): str}
)

_TRIP_FIELDS = {
    vol.Optional(CONF_TRIP_NAME): str,
    vol.Required(CONF_ORIGIN): str,
    vol.Required(CONF_DESTINATION): str,
    vol.Required(CONF_DATE_FROM): cv.date,
    vol.Required(CONF_DATE_TO): cv.date,
    vol.Optional(CONF_RETURN_FROM): cv.date,
    vol.Optional(CONF_RETURN_TO): cv.date,
    vol.Optional(CONF_PASSENGERS): vol.All(vol.Coerce(int), vol.Range(min=1, max=9)),
    vol.Optional(CONF_MAX_STOPS): vol.All(vol.Coerce(int), vol.Range(min=0, max=3)),
    vol.Optional(CONF_CURRENCY): str,
    vol.Optional(CONF_TARGET_PRICE): vol.Coerce(float),
    vol.Optional(CONF_NOTIFY_ON_TARGET): bool,
    vol.Optional(CONF_CHEAP_PERCENTILE): vol.All(
        vol.Coerce(float),
        vol.Range(min=MIN_CHEAP_PERCENTILE, max=MAX_CHEAP_PERCENTILE),
    ),
    vol.Optional(CONF_NOTIFY_ON_CHEAP): bool,
}

SERVICE_SCHEMA_ADD_TRIP = vol.Schema({vol.Optional(ATTR_ENTRY_ID): str, **_TRIP_FIELDS})
SERVICE_SCHEMA_UPDATE_TRIP = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): str,
        vol.Required(ATTR_TRIP_ID): str,
        **{
            key: default
            for key, default in _TRIP_FIELDS.items()
            if isinstance(key, vol.Optional)
        },
    }
)


def _get_target_entry(hass: HomeAssistant, entry_id: str | None = None):
    """Return the target config entry, or raise if not found."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if entry_id:
        target = next((e for e in entries if e.entry_id == entry_id), None)
        if target is None:
            raise HomeAssistantError(
                f"No {DOMAIN} config entry found for entry_id '{entry_id}'"
            )
        return target
    if not entries:
        raise HomeAssistantError(f"No {DOMAIN} config entry is available")
    return entries[0]


def _update_entry_options(hass: HomeAssistant, entry, update: dict[str, Any]) -> None:
    """Merge updates into entry options (triggers the reload listener)."""
    options = {**entry.options, **update}
    hass.config_entries.async_update_entry(entry, options=options)


def _entry_provider(hass: HomeAssistant, entry) -> Any:
    return get_provider(
        entry.data.get(CONF_PROVIDER, DEFAULT_PROVIDER),
        hass,
        entry.data.get(CONF_API_KEY, ""),
        base_url=entry.data.get(CONF_BASE_URL) or None,
    )


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register domain services (idempotent across entries)."""
    if hass.data.get(SERVICES_REGISTERED):
        return

    async def _async_refresh(call: ServiceCall) -> None:
        entry = _get_target_entry(hass, call.data.get(ATTR_ENTRY_ID))
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        await coordinator.async_request_refresh()

    async def _async_add_trip(call: ServiceCall) -> None:
        entry = _get_target_entry(hass, call.data.get(ATTR_ENTRY_ID))
        data = dict(call.data)
        data.pop(ATTR_ENTRY_ID, None)
        errors = validate_trip_form(data)
        if errors:
            raise HomeAssistantError(
                f"Invalid trip definition: {', '.join(errors.values())}"
            )
        trips = list(entry.options.get(CONF_TRIPS, []))
        if len(trips) >= MAX_TRIPS:
            raise HomeAssistantError("Maximum number of trips reached")
        existing = [trip["id"] for trip in trips]
        origin = str(data.get(CONF_ORIGIN, "")).strip()
        destination = str(data.get(CONF_DESTINATION, "")).strip()
        name = str(data.get(CONF_TRIP_NAME, "")).strip() or f"{origin} → {destination}"
        trip = trip_dict_from_form(
            data,
            trip_id=make_trip_id(origin, destination, existing),
            name=name,
        )
        trips.append(trip)
        _update_entry_options(hass, entry, {CONF_TRIPS: trips})

    async def _async_update_trip(call: ServiceCall) -> None:
        entry = _get_target_entry(hass, call.data.get(ATTR_ENTRY_ID))
        trip_id = call.data[ATTR_TRIP_ID]
        trips = list(entry.options.get(CONF_TRIPS, []))
        trip = next((t for t in trips if t["id"] == trip_id), None)
        if trip is None:
            raise HomeAssistantError(f"No trip found with id '{trip_id}'")
        data = {
            **trip,
            **{
                k: v
                for k, v in call.data.items()
                if k not in (ATTR_ENTRY_ID, ATTR_TRIP_ID)
            },
        }
        errors = validate_trip_form(data)
        if errors:
            raise HomeAssistantError(
                f"Invalid trip update: {', '.join(errors.values())}"
            )
        name = str(data.get(CONF_TRIP_NAME, "")).strip() or trip["name"]
        updated = trip_dict_from_form(data, trip_id=trip_id, name=name)
        trips = [updated if t["id"] == trip_id else t for t in trips]
        _update_entry_options(hass, entry, {CONF_TRIPS: trips})

    async def _async_remove_trip(call: ServiceCall) -> None:
        entry = _get_target_entry(hass, call.data.get(ATTR_ENTRY_ID))
        trip_id = call.data[ATTR_TRIP_ID]
        trips = list(entry.options.get(CONF_TRIPS, []))
        if trip_id not in [t["id"] for t in trips]:
            raise HomeAssistantError(f"No trip found with id '{trip_id}'")
        trips = [t for t in trips if t["id"] != trip_id]
        _update_entry_options(hass, entry, {CONF_TRIPS: trips})

    async def _async_resolve_location(call: ServiceCall) -> dict:
        entry = _get_target_entry(hass, call.data.get(ATTR_ENTRY_ID))
        provider = _entry_provider(hass, entry)
        try:
            locations = await provider.resolve_location(call.data[ATTR_QUERY])
        except ProviderError as err:
            raise HomeAssistantError(str(err)) from err
        return {"locations": [asdict(loc) for loc in locations]}

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        _async_refresh,
        schema=SERVICE_SCHEMA_REFRESH,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_TRIP,
        _async_add_trip,
        schema=SERVICE_SCHEMA_ADD_TRIP,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_TRIP,
        _async_update_trip,
        schema=SERVICE_SCHEMA_UPDATE_TRIP,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_TRIP,
        _async_remove_trip,
        schema=SERVICE_SCHEMA_REMOVE_TRIP,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESOLVE_LOCATION,
        _async_resolve_location,
        schema=SERVICE_SCHEMA_RESOLVE,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.data[SERVICES_REGISTERED] = True


async def async_unload_services(hass: HomeAssistant, current_entry=None) -> None:
    """Unload domain services when no other entry remains."""
    remaining = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if current_entry is None or entry.entry_id != current_entry.entry_id
    ]
    if remaining:
        return
    if not hass.data.get(SERVICES_REGISTERED):
        return
    for service in (
        SERVICE_REFRESH,
        SERVICE_ADD_TRIP,
        SERVICE_UPDATE_TRIP,
        SERVICE_REMOVE_TRIP,
        SERVICE_RESOLVE_LOCATION,
    ):
        hass.services.async_remove(DOMAIN, service)
    hass.data[SERVICES_REGISTERED] = False
