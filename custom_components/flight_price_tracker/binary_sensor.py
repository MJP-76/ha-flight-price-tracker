"""Binary sensor platform for the Flight Price Tracker integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FlightPriceCoordinator
from .models import offer_display_attributes


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FlightPriceCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    dev_reg = dr.async_get(hass)
    entities: list[BinarySensorEntity] = []
    for trip in coordinator.trips:
        if trip.target_price is None:
            continue
        device = dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, trip.id)},
            name=trip.name,
            manufacturer="Flight Price Tracker",
            model="Trip",
        )
        entities.append(TargetMetSensor(coordinator, trip.id, device))
    async_add_entities(entities)


class TargetMetSensor(CoordinatorEntity[FlightPriceCoordinator], BinarySensorEntity):
    """ON while the best price found is at or below the trip target price."""

    _attr_translation_key = "target_met"
    _attr_icon = "mdi:gift-outline"
    _attr_has_entity_name = True

    def __init__(self, coordinator, trip_id: str, device) -> None:
        super().__init__(coordinator)
        self.trip_id = trip_id
        self._attr_device = device
        self._attr_unique_id = f"{DOMAIN}_{trip_id}_target_met"

    @property
    def _info(self) -> dict:
        return self.coordinator.data.get(self.trip_id, {})

    @property
    def is_on(self) -> bool:
        return bool(self._info.get("target_met"))

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict:
        info = self._info
        attrs = offer_display_attributes(info.get("offer"))
        attrs.update(
            {
                "target_price": self._info.get("target_price"),
                "currency": info.get("currency"),
                "origin": info.get("origin"),
                "destination": info.get("destination"),
                "trip_id": self.trip_id,
                "last_updated": info.get("last_updated"),
            }
        )
        return attrs
