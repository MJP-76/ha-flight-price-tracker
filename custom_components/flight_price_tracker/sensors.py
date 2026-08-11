"""Sensor platform for the Flight Price Tracker integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
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
    entities: list[SensorEntity] = []
    for trip in coordinator.trips:
        device = dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, trip.id)},
            name=trip.name,
            manufacturer="Flight Price Tracker",
            model="Trip",
        )
        entities.extend(
            [
                BestPriceSensor(coordinator, trip.id, trip.currency, device),
                LowestPriceSensor(coordinator, trip.id, trip.currency, device),
                OffersCountSensor(coordinator, trip.id, device),
            ]
        )
    async_add_entities(entities)


class FlightPriceSensor(CoordinatorEntity[FlightPriceCoordinator], SensorEntity):
    """Base sensor bound to a trip."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, trip_id: str, currency: str, device) -> None:
        super().__init__(coordinator)
        self.trip_id = trip_id
        self._attr_device = device
        self._attr_native_unit_of_measurement = currency or None
        self._attr_currency = currency

    @property
    def _info(self) -> dict:
        return self.coordinator.data.get(self.trip_id, {})


class BestPriceSensor(FlightPriceSensor):
    """Current best (lowest) price seen for the trip on the latest poll."""

    _attr_translation_key = "best_price"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:airplane"

    def __init__(self, coordinator, trip_id, currency, device) -> None:
        super().__init__(coordinator, trip_id, currency, device)
        self._attr_unique_id = f"{DOMAIN}_{trip_id}_best_price"

    @property
    def native_value(self) -> float | None:
        return self._info.get("best_price")

    @property
    def extra_state_attributes(self) -> dict:
        info = self._info
        attrs = offer_display_attributes(info.get("offer"))
        attrs.update(
            {
                "currency": self._attr_currency,
                "provider": info.get("offer", {}).get("provider")
                if info.get("offer")
                else None,
                "offers_count": info.get("offers_count"),
                "origin": info.get("origin"),
                "destination": info.get("destination"),
                "max_stops": info.get("max_stops"),
                "passengers": info.get("passengers"),
                "trip_id": self.trip_id,
                "last_updated": info.get("last_updated"),
            }
        )
        return attrs


class LowestPriceSensor(FlightPriceSensor):
    """Lowest price recorded for the trip since tracking began."""

    _attr_translation_key = "lowest_price"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:trending-down"

    def __init__(self, coordinator, trip_id, currency, device) -> None:
        super().__init__(coordinator, trip_id, currency, device)
        self._attr_unique_id = f"{DOMAIN}_{trip_id}_lowest_price"

    @property
    def native_value(self) -> float | None:
        return self._info.get("lowest_seen")

    @property
    def extra_state_attributes(self) -> dict:
        attrs = offer_display_attributes(self._info.get("lowest_seen_offer"))
        attrs.update(
            {
                "currency": self._attr_currency,
                "trip_id": self.trip_id,
                "last_updated": self._info.get("last_updated"),
            }
        )
        return attrs


class OffersCountSensor(FlightPriceSensor):
    """How many itineraries the latest poll returned."""

    _attr_translation_key = "offers_count"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, trip_id, device) -> None:
        super().__init__(coordinator, trip_id, "", device)
        self._attr_unique_id = f"{DOMAIN}_{trip_id}_offers_count"

    @property
    def native_value(self) -> int | None:
        return self._info.get("offers_count")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success or "offers_count" in self._info
