"""Coordinator for the Flight Price Tracker integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import storage
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_SCAN_INTERVAL_HOURS,
    CONF_TRIPS,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
)
from .models import (
    TripConfig,
    best_offer,
    evaluate_update,
    update_daily_history,
)
from .providers import FlightSearchProvider, ProviderAuthError, ProviderError

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = f"{DOMAIN}.state"
STORAGE_VERSION = 1

EVENT_TARGET_REACHED = f"{DOMAIN}_target_reached"
EVENT_NEW_LOW = f"{DOMAIN}_new_low"
EVENT_HISTORICALLY_CHEAP = f"{DOMAIN}_historically_cheap"


class FlightPriceCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls every trip's price and tracks lowest-seen + target state."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        provider: FlightSearchProvider,
    ) -> None:
        self.entry = entry
        self.provider = provider
        interval_hours = entry.options.get(
            CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=interval_hours),
            always_update=True,
        )
        self._store = storage.Store[dict[str, dict[str, dict[str, Any]]]](
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self.data: dict[str, dict[str, Any]] = {}
        self.auth_failed = False

    @property
    def trips(self) -> list[TripConfig]:
        trips = self.entry.options.get(CONF_TRIPS, [])
        return [TripConfig.from_dict(trip) for trip in trips]

    async def _async_setup(self) -> None:
        stored = await self._store.async_load()
        if stored and self.entry.entry_id in stored:
            self.data = stored[self.entry.entry_id]

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        for trip in self.trips:
            await self._async_update_trip(trip)
        await self._async_save()
        return self.data

    async def _async_update_trip(self, trip: TripConfig) -> None:
        info = self.data.setdefault(trip.id, {})
        info.setdefault("lowest_seen", None)
        try:
            offers = await self.provider.search(trip)
        except ProviderAuthError as err:
            _LOGGER.warning("Authentication failed for trip '%s': %s", trip.name, err)
            self.auth_failed = True
            info["last_error"] = str(err)
            info["last_updated"] = info.get("last_updated")
            return
        except ProviderError as err:
            _LOGGER.warning("Flight search failed for trip '%s': %s", trip.name, err)
            info["last_error"] = str(err)
            info["last_updated"] = info.get("last_updated")
            return
        except Exception as err:
            _LOGGER.exception("Unexpected error searching trip '%s'", trip.name)
            info["last_error"] = f"Unexpected error: {err}"
            info["last_updated"] = info.get("last_updated")
            return

        offer = best_offer(offers)
        history = info.get("price_history") or []
        if offer is not None:
            today = datetime.now(timezone.utc).astimezone().date()
            history = update_daily_history(history, today, offer.price)
        result = evaluate_update(trip, info, offers, history=history)
        self.data[trip.id] = result["info"]

        if result["new_low"] and result["offer"] is not None:
            self._fire_new_low(trip, result["offer"])
        if result["fire_target_reached"] and result["offer"] is not None:
            self._fire_target_reached(trip, result["offer"])
        if result["fire_historically_cheap"]:
            self._fire_historically_cheap(trip, result["info"])

    def _event_data(self, trip: TripConfig, offer) -> dict[str, Any]:
        return {
            "trip_id": trip.id,
            "trip_name": trip.name,
            "origin": trip.origin,
            "destination": trip.destination,
            "price": offer.price,
            "currency": offer.currency,
            "stops": offer.stops,
            "deep_link": offer.deep_link,
        }

    def _fire_new_low(self, trip: TripConfig, offer) -> None:
        self.hass.bus.async_fire(EVENT_NEW_LOW, self._event_data(trip, offer))

    def _fire_target_reached(self, trip: TripConfig, offer) -> None:
        data = self._event_data(trip, offer)
        self.hass.bus.async_fire(EVENT_TARGET_REACHED, data)
        if trip.notify_on_target and trip.target_price is not None:
            from homeassistant.components import persistent_notification

            price_text = f"{offer.price:,.0f}"
            target_text = f"{trip.target_price:,.0f}"
            if offer.deep_link:
                message = (
                    f"{trip.origin} → {trip.destination} is now **{offer.currency} "
                    f"{price_text}** (target {offer.currency} {target_text}).\n\n"
                    f"[Book on Kiwi.com]({offer.deep_link})"
                )
            else:
                message = (
                    f"{trip.origin} → {trip.destination} is now **{offer.currency} "
                    f"{price_text}** (target {offer.currency} {target_text})."
                )
            persistent_notification.async_create(
                self.hass,
                message,
                title=f"Flight price target reached: {trip.name}",
                notification_id=f"{DOMAIN}_target_{trip.id}",
            )
            _LOGGER.info(
                "Target reached for trip '%s' at %s %s",
                trip.name,
                offer.currency,
                offer.price,
            )

    def _fire_historically_cheap(self, trip: TripConfig, info: dict[str, Any]) -> None:
        data = {
            "trip_id": trip.id,
            "trip_name": trip.name,
            "origin": trip.origin,
            "destination": trip.destination,
            "price": info.get("best_price"),
            "currency": info.get("currency"),
            "stops": info.get("max_stops"),
            "current_percentile": info.get("current_percentile"),
            "avg_price": info.get("avg_price"),
            "cheap_threshold": info.get("cheap_threshold"),
            "price_history_count": info.get("price_history_count"),
            "cheap_percentile": info.get("cheap_percentile"),
        }
        self.hass.bus.async_fire(EVENT_HISTORICALLY_CHEAP, data)
        if trip.notify_on_cheap:
            from homeassistant.components import persistent_notification

            price = info.get("best_price")
            currency = info.get("currency", "GBP")
            price_text = f"{price:,.0f}" if price is not None else "n/a"
            message = (
                f"{trip.origin} → {trip.destination} is **{currency} {price_text}** — "
                f"in the cheapest {round((info.get('cheap_percentile') or 0.25) * 100)}% "
                f"of the {info.get('price_history_count', 0)} daily prices we've seen "
                f"(avg {currency} "
                f"{info.get('avg_price'):,.0f})."
            )
            persistent_notification.async_create(
                self.hass,
                message,
                title=f"Flight price is historically cheap: {trip.name}",
                notification_id=f"{DOMAIN}_cheap_{trip.id}",
            )
            _LOGGER.info(
                "Historically cheap for trip '%s' at %s %s (percentile %s)",
                trip.name,
                currency,
                price,
                info.get("current_percentile"),
            )

    async def _async_save(self) -> None:
        stored = await self._store.async_load() or {}
        stored[self.entry.entry_id] = self.data
        await self._store.async_save(stored)
