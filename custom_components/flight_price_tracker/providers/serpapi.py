"""SerpAPI Google Flights provider.

Uses SerpAPI's ``google_flights`` engine to search Google Flights data.
Requires a SerpAPI API key (free tier: 100–250 searches/month).

Endpoint: ``GET https://serpapi.com/search?engine=google_flights&...``

Round-trip searches require two API calls: one for outbound flights, then a
second using the ``departure_token`` from the cheapest outbound result to fetch
return flights.  This keeps search count low while still producing accurate
round-trip prices.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiohttp import ClientError

from ..models import FlightLeg, FlightOffer, LocationResult, TripConfig
from . import (
    FlightSearchProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitedError,
    register_provider,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://serpapi.com"
SEARCH_PATH = "/search"
LOCATIONS_PATH = "/search"


@register_provider
class SerpAPIProvider(FlightSearchProvider):
    """Google Flights search via SerpAPI."""

    name = "serpapi"
    display_name = "Google Flights (SerpAPI)"

    def __init__(self, hass, api_key: str = "", **options) -> None:
        super().__init__(hass, api_key=api_key, **options)
        self.base_url = (options.get("base_url") or DEFAULT_BASE_URL).rstrip("/")

    async def search(self, trip: TripConfig) -> list[FlightOffer]:
        params = self._build_params(trip)
        data = await self._request(params)

        outbound_offers = self._parse_flights(
            data, fallback_currency=trip.currency
        )

        if not trip.is_round_trip:
            return outbound_offers

        # Round trip: use departure_token from cheapest outbound to get
        # return flights, then merge into a single round-trip offer.
        cheapest = min(outbound_offers, key=lambda o: o.price) if outbound_offers else None
        if cheapest is None:
            return []

        dep_token = getattr(cheapest, "_departure_token", None)
        if not dep_token:
            _LOGGER.warning(
                "No departure_token on cheapest outbound for '%s'; "
                "returning outbound-only results",
                trip.name,
            )
            return outbound_offers

        return_legs = await self._fetch_return_flights(dep_token, trip.currency)
        if not return_legs:
            return outbound_offers

        return [
            FlightOffer(
                price=cheapest.price,
                currency=cheapest.currency,
                outbound=cheapest.outbound,
                return_legs=return_legs,
                deep_link=cheapest.deep_link,
                booking_token=cheapest.booking_token,
                provider=self.name,
                fetched_at=datetime.now(timezone.utc),
            )
        ]

    async def _request(self, params: dict) -> dict:
        try:
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
        except ImportError:
            from homeassistant.helpers.aiohttp_client import (  # type: ignore[no-redef]
                async_get_clientsession,
            )

        session = self.options.get("session") or async_get_clientsession(self.hass)
        try:
            async with session.get(
                self.base_url + SEARCH_PATH,
                params=params,
            ) as resp:
                if resp.status in (401, 403):
                    raise ProviderAuthError(
                        f"SerpAPI rejected the API key (HTTP {resp.status})"
                    )
                if resp.status == 429:
                    raise ProviderRateLimitedError(
                        "SerpAPI rate limit exceeded (HTTP 429)"
                    )
                if resp.status >= 400:
                    raise ProviderError(
                        f"SerpAPI error (HTTP {resp.status}): "
                        f"{(await resp.text())[:500]}"
                    )
                return await resp.json()
        except (ProviderError, ProviderAuthError, ProviderRateLimitedError):
            raise
        except ClientError as err:
            raise ProviderError(f"Request to SerpAPI failed: {err}") from err

    @staticmethod
    def _fmt_date(value) -> str | None:
        if value is None:
            return None
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        return str(value)

    def _build_params(self, trip: TripConfig) -> dict:
        params: dict = {
            "engine": "google_flights",
            "api_key": self.api_key,
            "departure_id": trip.origin,
            "arrival_id": trip.destination,
            "outbound_date": self._fmt_date(trip.date_from),
            "adults": trip.passengers,
            "currency": trip.currency,
            "hl": "en",
            "gl": "uk",
            "sort_by": "2",
        }
        if trip.is_round_trip:
            params["type"] = 1
            params["return_date"] = self._fmt_date(trip.return_from)
        else:
            params["type"] = 2

        # SerpAPI stops filter: 0=any, 1=nonstop, 2=≤1, 3=≤2
        max_stops = trip.max_stops
        if max_stops == 0:
            params["stops"] = 1
        elif max_stops == 1:
            params["stops"] = 2
        elif max_stops == 2:
            params["stops"] = 3
        # max_stops >= 3 → omit (any number of stops)

        return params

    def _parse_flights(
        self, data: dict, *, fallback_currency: str
    ) -> list[FlightOffer]:
        offers: list[FlightOffer] = []
        for item in data.get("best_flights") or []:
            parsed = self._parse_offer(item, fallback_currency)
            if parsed is not None:
                offers.append(parsed)
        for item in data.get("other_flights") or []:
            parsed = self._parse_offer(item, fallback_currency)
            if parsed is not None:
                offers.append(parsed)
        return offers

    def _parse_offer(self, item: dict, fallback_currency: str) -> FlightOffer | None:
        raw_price = item.get("price")
        try:
            price = float(raw_price)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            _LOGGER.warning("SerpAPI flight without a numeric price skipped")
            return None

        outbound = self._parse_legs(item.get("flights") or [])

        # Deep link: use Google Flights URL if booking_token is available
        booking_token = item.get("booking_token")
        deep_link = None
        if booking_token:
            deep_link = f"https://www.google.com/travel/flights?q=Flights+to+Destination+from+Origin"

        offer = FlightOffer(
            price=price,
            currency=item.get("currency") or fallback_currency,
            outbound=outbound,
            deep_link=deep_link,
            booking_token=booking_token,
            provider=self.name,
            fetched_at=datetime.now(timezone.utc),
        )
        # Stash departure_token for round-trip follow-up
        offer._departure_token = item.get("departure_token")  # type: ignore[attr-defined]
        return offer

    @staticmethod
    def _parse_legs(flights: list) -> list[FlightLeg]:
        legs: list[FlightLeg] = []
        for segment in flights:
            dep_airport = segment.get("departure_airport") or {}
            arr_airport = segment.get("arrival_airport") or {}
            dep = SerpAPIProvider._parse_datetime(dep_airport.get("time"))
            arr = SerpAPIProvider._parse_datetime(arr_airport.get("time"))
            legs.append(
                FlightLeg(
                    airline=str(segment.get("airline", "")),
                    flight_number=str(segment.get("flight_number", "")),
                    origin=str(dep_airport.get("id", "")),
                    destination=str(arr_airport.get("id", "")),
                    departs_at=dep,
                    arrives_at=arr,
                )
            )
        return legs

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    async def _fetch_return_flights(
        self, departure_token: str, fallback_currency: str
    ) -> list[FlightLeg]:
        params = {
            "engine": "google_flights",
            "api_key": self.api_key,
            "departure_token": departure_token,
        }
        try:
            data = await self._request(params)
        except ProviderError as err:
            _LOGGER.warning("Failed to fetch return flights: %s", err)
            return []

        for item in data.get("best_flights") or []:
            legs = self._parse_legs(item.get("flights") or [])
            if legs:
                return legs
        for item in data.get("other_flights") or []:
            legs = self._parse_legs(item.get("flights") or [])
            if legs:
                return legs
        _LOGGER.warning("No return flights found for departure_token")
        return []

    async def validate_credentials(self) -> str | None:
        params = {
            "engine": "google_flights",
            "api_key": self.api_key,
            "departure_id": "LHR",
            "arrival_id": "JFK",
            "outbound_date": self._fmt_date(
                datetime.now(timezone.utc).date()
            ),
            "type": 2,
        }
        try:
            await self._request(params)
        except ProviderAuthError as err:
            return str(err)
        except ProviderError as err:
            return str(err)
        return None

    async def resolve_location(self, query: str) -> list[LocationResult]:
        try:
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
        except ImportError:
            from homeassistant.helpers.aiohttp_client import (  # type: ignore[no-redef]
                async_get_clientsession,
            )

        session = self.options.get("session") or async_get_clientsession(self.hass)
        try:
            async with session.get(
                self.base_url + "/google_flights_api",
                params={
                    "engine": "google_flights",
                    "api_key": self.api_key,
                    "departure_id": query,
                    "type": 2,
                },
            ) as resp:
                if resp.status >= 400:
                    return []
                data = await resp.json()
        except Exception:
            return []

        results: list[LocationResult] = []
        for airport_group in data.get("airports") or []:
            for direction in ("departure", "arrival"):
                for info in airport_group.get(direction) or []:
                    airport = info.get("airport") or {}
                    code = airport.get("id")
                    if not code:
                        continue
                    results.append(
                        LocationResult(
                            code=str(code),
                            name=str(airport.get("name") or ""),
                            location_type="airport",
                            country=str(info.get("country") or ""),
                        )
                    )
        # Deduplicate by code
        seen: set[str] = set()
        unique: list[LocationResult] = []
        for r in results:
            if r.code not in seen:
                seen.add(r.code)
                unique.append(r)
        return unique[:10]
