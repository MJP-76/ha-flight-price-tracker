"""Shared data models and pure logic for the Flight Price Tracker integration.

This module deliberately avoids importing ``homeassistant`` so it can be unit
tested without a running Home Assistant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

DEFAULT_PASSENGERS = 1
DEFAULT_MAX_STOPS = 2
DEFAULT_CURRENCY = "GBP"
MAX_PASSENGERS = 9


@dataclass
class TripConfig:
    """A single tracked trip definition, stored as JSON in entry options."""

    id: str
    name: str
    origin: str
    destination: str
    date_from: date
    date_to: date
    return_from: date | None = None
    return_to: date | None = None
    passengers: int = DEFAULT_PASSENGERS
    max_stops: int = DEFAULT_MAX_STOPS
    currency: str = DEFAULT_CURRENCY
    target_price: float | None = None
    notify_on_target: bool = True

    @property
    def is_round_trip(self) -> bool:
        return self.return_from is not None and self.return_to is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "origin": self.origin,
            "destination": self.destination,
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
            "return_from": self.return_from.isoformat() if self.return_from else None,
            "return_to": self.return_to.isoformat() if self.return_to else None,
            "passengers": self.passengers,
            "max_stops": self.max_stops,
            "currency": self.currency,
            "target_price": self.target_price,
            "notify_on_target": self.notify_on_target,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TripConfig:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            origin=str(data["origin"]),
            destination=str(data["destination"]),
            date_from=date.fromisoformat(str(data["date_from"])),
            date_to=date.fromisoformat(str(data["date_to"])),
            return_from=(
                date.fromisoformat(str(data["return_from"]))
                if data.get("return_from")
                else None
            ),
            return_to=(
                date.fromisoformat(str(data["return_to"]))
                if data.get("return_to")
                else None
            ),
            passengers=int(data.get("passengers", DEFAULT_PASSENGERS)),
            max_stops=int(data.get("max_stops", DEFAULT_MAX_STOPS)),
            currency=str(data.get("currency", DEFAULT_CURRENCY)),
            target_price=(
                float(data["target_price"])
                if data.get("target_price") is not None
                else None
            ),
            notify_on_target=bool(data.get("notify_on_target", True)),
        )


@dataclass
class FlightLeg:
    """A single flight segment."""

    airline: str
    flight_number: str
    origin: str
    destination: str
    departs_at: datetime | None
    arrives_at: datetime | None
    is_return: bool = False


@dataclass
class FlightOffer:
    """A normalized itinerary returned by any provider."""

    price: float
    currency: str
    outbound: list[FlightLeg] = field(default_factory=list)
    return_legs: list[FlightLeg] = field(default_factory=list)
    deep_link: str | None = None
    booking_token: str | None = None
    provider: str = ""
    fetched_at: datetime | None = None

    @property
    def is_round_trip(self) -> bool:
        return bool(self.return_legs)

    @property
    def stops(self) -> int:
        return max(len(self.outbound) - 1, 0)

    @property
    def return_stops(self) -> int:
        return max(len(self.return_legs) - 1, 0)

    @property
    def total_duration_minutes(self) -> int | None:
        total = 0
        if (
            self.outbound
            and self.outbound[0].departs_at
            and self.outbound[-1].arrives_at
        ):
            total += int(
                (
                    self.outbound[-1].arrives_at - self.outbound[0].departs_at
                ).total_seconds()
                // 60
            )
        if (
            self.return_legs
            and self.return_legs[0].departs_at
            and self.return_legs[-1].arrives_at
        ):
            total += int(
                (
                    self.return_legs[-1].arrives_at - self.return_legs[0].departs_at
                ).total_seconds()
                // 60
            )
        return total if total else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "price": self.price,
            "currency": self.currency,
            "outbound": [_leg_to_dict(leg) for leg in self.outbound],
            "return_legs": [_leg_to_dict(leg) for leg in self.return_legs],
            "deep_link": self.deep_link,
            "booking_token": self.booking_token,
            "provider": self.provider,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlightOffer:
        return cls(
            price=float(data["price"]),
            currency=str(data.get("currency", "")),
            outbound=[_leg_from_dict(leg) for leg in data.get("outbound", [])],
            return_legs=[_leg_from_dict(leg) for leg in data.get("return_legs", [])],
            deep_link=data.get("deep_link"),
            booking_token=data.get("booking_token"),
            provider=str(data.get("provider", "")),
            fetched_at=_parse_dt(data.get("fetched_at")),
        )


@dataclass
class LocationResult:
    """A location suggestion from a provider's geocoding endpoint."""

    code: str
    name: str
    location_type: str
    country: str | None = None


def _leg_to_dict(leg: FlightLeg) -> dict[str, Any]:
    return {
        "airline": leg.airline,
        "flight_number": leg.flight_number,
        "origin": leg.origin,
        "destination": leg.destination,
        "departs_at": leg.departs_at.isoformat() if leg.departs_at else None,
        "arrives_at": leg.arrives_at.isoformat() if leg.arrives_at else None,
        "is_return": leg.is_return,
    }


def _leg_from_dict(data: dict[str, Any]) -> FlightLeg:
    return FlightLeg(
        airline=str(data.get("airline", "")),
        flight_number=str(data.get("flight_number", "")),
        origin=str(data.get("origin", "")),
        destination=str(data.get("destination", "")),
        departs_at=_parse_dt(data.get("departs_at")),
        arrives_at=_parse_dt(data.get("arrives_at")),
        is_return=bool(data.get("is_return", False)),
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def best_offer(offers: list[FlightOffer]) -> FlightOffer | None:
    """Return the cheapest offer, or None when there are no results."""
    if not offers:
        return None
    return min(offers, key=lambda offer: offer.price)


def slugify(value: str) -> str:
    """Slug used for trip ids / entity ids (mirrors Home Assistant slugify)."""
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def validate_trip_form(data: dict[str, Any]) -> dict[str, str]:
    """Validate raw form input shared by the config flow and trip services.

    Returns a dict of {field: error_key}; empty dict means valid.
    """
    errors: dict[str, str] = {}

    origin = str(data.get("origin", "")).strip()
    destination = str(data.get("destination", "")).strip()
    if not origin:
        errors["origin"] = "required"
    if not destination:
        errors["destination"] = "required"
    if origin.upper() == destination.upper() and origin:
        errors["destination"] = "same_origin_destination"

    try:
        date_from = date.fromisoformat(str(data["date_from"]))
    except (KeyError, ValueError):
        errors["date_from"] = "invalid_date"
        date_from = None
    try:
        date_to = date.fromisoformat(str(data["date_to"]))
    except (KeyError, ValueError):
        errors["date_to"] = "invalid_date"
        date_to = None

    if date_from and date_to and date_to < date_from:
        errors["date_to"] = "date_to_before_from"

    passengers = data.get("passengers")
    if passengers is not None:
        try:
            if not 1 <= int(passengers) <= MAX_PASSENGERS:
                errors["passengers"] = "passengers_range"
        except (TypeError, ValueError):
            errors["passengers"] = "invalid_passengers"

    if data.get("max_stops") is not None:
        try:
            if not 0 <= int(data["max_stops"]) <= 3:
                errors["max_stops"] = "max_stops_range"
        except (TypeError, ValueError):
            errors["max_stops"] = "invalid_max_stops"

    target = data.get("target_price")
    if target not in (None, ""):
        try:
            if float(target) <= 0:
                errors["target_price"] = "target_positive"
        except (TypeError, ValueError):
            errors["target_price"] = "target_positive"

    return_f = data.get("return_from")
    return_t = data.get("return_to")
    if return_f:
        try:
            return_from = date.fromisoformat(str(return_f))
        except ValueError:
            errors["return_from"] = "invalid_date"
            return_from = None
    else:
        return_from = None
    if return_t:
        try:
            return_to = date.fromisoformat(str(return_t))
        except ValueError:
            errors["return_to"] = "invalid_date"
            return_to = None
    else:
        return_to = None

    if return_from and return_to and return_to < return_from:
        errors["return_to"] = "return_to_before_from"
    if return_from and date_to and return_from < date_to:
        errors["return_from"] = "return_before_departure"

    return errors


def trip_dict_from_form(
    form: dict[str, Any], *, trip_id: str, name: str
) -> dict[str, Any]:
    """Build a serializable trip dict from raw form/service input."""
    origin = str(form.get("origin", "")).strip().upper()
    destination = str(form.get("destination", "")).strip().upper()
    return {
        "id": trip_id,
        "name": name,
        "origin": origin,
        "destination": destination,
        "date_from": str(form["date_from"]),
        "date_to": str(form["date_to"]),
        "return_from": str(form.get("return_from") or "") or None,
        "return_to": str(form.get("return_to") or "") or None,
        "passengers": int(form.get("passengers", DEFAULT_PASSENGERS)),
        "max_stops": int(form.get("max_stops", DEFAULT_MAX_STOPS)),
        "currency": str(form.get("currency", DEFAULT_CURRENCY)),
        "target_price": (
            float(form["target_price"])
            if form.get("target_price") not in (None, "")
            else None
        ),
        "notify_on_target": bool(form.get("notify_on_target", True)),
    }


def make_trip_id(origin: str, destination: str, existing_ids: list[str]) -> str:
    """Generate a stable, human-readable unique trip id."""
    base = f"{slugify(origin)}_to_{slugify(destination)}"
    candidate = base
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def evaluate_update(
    trip: TripConfig, info: dict[str, Any], offers: list[FlightOffer]
) -> dict[str, Any]:
    """Pure per-poll update logic: compute new state, new-low and target events.

    ``info`` is the previous per-trip state dict. Returns a dict with the new
    ``info`` plus ``new_low`` and ``fire_target_reached`` booleans.
    """
    now = datetime.now(timezone.utc)
    offer = best_offer(offers)

    prev_low = info.get("lowest_seen")
    lowest_seen = prev_low
    lowest_seen_offer = info.get("lowest_seen_offer")
    new_low = False

    if offer is not None:
        if prev_low is None:
            lowest_seen = offer.price
            lowest_seen_offer = offer.to_dict()
        elif offer.price < prev_low:
            lowest_seen = offer.price
            lowest_seen_offer = offer.to_dict()
            new_low = True

    target = trip.target_price
    target_met = bool(
        target is not None and offer is not None and offer.price <= target
    )
    fire_target_reached = target_met and not bool(info.get("target_was_met"))

    new_info = {
        **info,
        "best_price": offer.price if offer else None,
        "currency": trip.currency,
        "offers_count": len(offers),
        "last_updated": now.isoformat(),
        "last_error": None,
        "offer": offer.to_dict() if offer else None,
        "lowest_seen": lowest_seen,
        "lowest_seen_offer": lowest_seen_offer,
        "target_met": target_met,
        "target_was_met": target_met,
        "trip_name": trip.name,
        "origin": trip.origin,
        "destination": trip.destination,
        "max_stops": trip.max_stops,
        "passengers": trip.passengers,
        "target_price": trip.target_price,
        "notify_on_target": trip.notify_on_target,
    }

    return {
        "info": new_info,
        "new_low": new_low,
        "fire_target_reached": fire_target_reached,
        "offer": offer,
    }


def offer_display_attributes(offer_dict: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten an offer dict into entity attribute material."""
    if not offer_dict:
        return {}
    legs = offer_dict.get("outbound", []) + offer_dict.get("return_legs", [])
    airlines = sorted({leg["airline"] for leg in legs if leg.get("airline")})
    flight_numbers = [leg["flight_number"] for leg in legs if leg.get("flight_number")]
    outbound = offer_dict.get("outbound", [])
    return_legs = offer_dict.get("return_legs", [])
    departure = outbound[0]["departs_at"] if outbound else None
    arrival = (
        return_legs[-1]["arrives_at"]
        if return_legs
        else (outbound[-1]["arrives_at"] if outbound else None)
    )
    return {
        "airlines": ", ".join(airlines) or "unknown",
        "flight_numbers": ", ".join(flight_numbers) or "unknown",
        "outbound_stops": max(len(outbound) - 1, 0) if outbound else None,
        "return_stops": max(len(return_legs) - 1, 0) if return_legs else None,
        "departure": departure,
        "arrival": arrival,
        "deep_link": offer_dict.get("deep_link"),
        "booking_token": offer_dict.get("booking_token"),
        "provider": offer_dict.get("provider"),
        "fetched_at": offer_dict.get("fetched_at"),
    }
