"""Deterministic mock provider for testing the integration without an API key.

Prices are stable per trip/date so polling behaves like a real provider, and
the ``deep_link`` is a placeholder. Select the ``mock`` provider in the config
flow to exercise sensors, automations and the dashboard end-to-end.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta, timezone

from ..models import FlightLeg, FlightOffer, TripConfig
from . import FlightSearchProvider, register_provider

AIRLINES = ["AA", "BA", "DL", "LH", "KL", "AF", "FR", "U2"]


@register_provider
class MockProvider(FlightSearchProvider):
    """Generates plausible, deterministic prices for a route/date pair."""

    name = "mock"
    display_name = "Mock (test data)"

    @staticmethod
    def _seed(trip: TripConfig) -> int:
        key = (
            f"{trip.origin}|{trip.destination}|{trip.date_from}|{trip.date_to}|"
            f"{trip.return_from}|{trip.return_to}|{trip.passengers}"
        ).lower()
        return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")

    def _make_legs(
        self,
        origin: str,
        destination: str,
        start: date,
        end: date,
        stops: int,
        rng: random.Random,
        is_return: bool,
    ) -> list[FlightLeg]:
        day = start + timedelta(days=rng.randint(0, max((end - start).days, 0)))
        legs: list[FlightLeg] = []
        dep = datetime(
            day.year, day.month, day.day, rng.randint(5, 21), 0, tzinfo=timezone.utc
        )
        for index in range(stops + 1):
            airline = rng.choice(AIRLINES)
            arr = dep + timedelta(
                hours=rng.randint(1, 5), minutes=rng.choice([0, 15, 30, 45])
            )
            legs.append(
                FlightLeg(
                    airline=airline,
                    flight_number=f"{airline}{rng.randint(100, 999)}",
                    origin=origin if index == 0 else destination,
                    destination=destination,
                    departs_at=dep,
                    arrives_at=arr,
                    is_return=is_return,
                )
            )
            dep = arr + timedelta(hours=rng.randint(2, 6))
        return legs

    async def search(self, trip: TripConfig) -> list[FlightOffer]:
        rng = random.Random(self._seed(trip))
        max_stops = trip.max_stops
        outbound = self._make_legs(
            trip.origin,
            trip.destination,
            trip.date_from,
            trip.date_to,
            rng.randint(0, max_stops),
            rng,
            is_return=False,
        )
        return_legs: list[FlightLeg] = []
        if trip.is_round_trip:
            assert trip.return_from is not None and trip.return_to is not None
            return_legs = self._make_legs(
                trip.destination,
                trip.origin,
                trip.return_from,
                trip.return_to,
                rng.randint(0, max_stops),
                rng,
                is_return=True,
            )
        price = round(
            float(60 + rng.randint(0, 900) + len(outbound) * rng.randint(20, 90)),
            2,
        )
        if return_legs:
            price += 40 + rng.randint(0, 300)
        return [
            FlightOffer(
                price=price,
                currency=trip.currency,
                outbound=outbound,
                return_legs=return_legs,
                deep_link=(
                    "https://example.com/mock-book"
                    f"?from={trip.origin}&to={trip.destination}"
                ),
                provider=self.name,
                fetched_at=datetime.now(timezone.utc),
            )
        ]

    async def validate_credentials(self) -> str | None:
        return None

    async def resolve_location(self, query: str) -> list:
        return []
