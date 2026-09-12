"""SerpAPI Google Flights provider.

Uses SerpAPI's ``google_flights`` engine to search Google Flights data.
Requires a SerpAPI API key (free tier: 100-250 searches/month).

Endpoint: ``GET https://serpapi.com/search?engine=google_flights&...``

Round-trip search (``type=1`` + ``return_date``) returns each itinerary's
outbound legs in ``flights`` plus the combined price and a ``departure_token``;
the return legs require a **second** call passing that token. The cheapest
itinerary's return legs are fetched and merged into a single ``FlightOffer``.

To keep the free-tier quota usable, results are cached per trip for a short
TTL and HTTP 429 / 5xx responses are retried with exponential backoff. Account
quota is refreshed from the ``/account`` endpoint (no search credit consumed).
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

from aiohttp import ClientError

from ..locations import coerce_code, search_locations
from ..models import FlightLeg, FlightOffer, LocationResult, PriceInsights, TripConfig
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

DEFAULT_HL = "en"
DEFAULT_GL = "uk"

# How long a per-trip result set is reused before SerpAPI is contacted again.
CACHE_TTL = timedelta(hours=1)
CACHE_MAX_ENTRIES = 32

# How often account quota (consuming no search credits) is re-fetched.
USAGE_TTL = timedelta(hours=6)

# Transient error (429 / 5xx / network) retries with backoff.
MAX_ATTEMPTS = 3


@register_provider
class SerpAPIProvider(FlightSearchProvider):
    """Google Flights search via SerpAPI."""

    name = "serpapi"
    display_name = "Google Flights (SerpAPI)"

    def __init__(self, hass, api_key: str = "", **options) -> None:
        super().__init__(hass, api_key=api_key, **options)
        self.base_url = (options.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        self.hl = str(options.get("hl") or DEFAULT_HL)
        self.gl = str(options.get("gl") or DEFAULT_GL)
        self._cache: dict[str, tuple[datetime, list[FlightOffer]]] = {}
        self._insights: dict[str, PriceInsights | None] = {}
        self.used_quota: int | None = None
        self.quota_remaining: int | None = None
        self.quota_per_month: int | None = None
        self._usage_checked: datetime | None = None

    async def search(self, trip: TripConfig) -> list[FlightOffer]:
        """Return the cheapest itineraries for the trip (TTL-cached)."""
        key = self._cache_key(trip)
        now = datetime.now(timezone.utc)
        hit = self._cache.get(key)
        if hit is not None and (now - hit[0]) < CACHE_TTL:
            return hit[1]
        offers, insights = await self._search_fresh(trip)
        if len(self._cache) >= CACHE_MAX_ENTRIES:
            evicted = next(iter(self._cache))
            self._cache.pop(evicted, None)
            self._insights.pop(evicted, None)
        self._cache[key] = (now, offers)
        self._insights[key] = insights
        return offers

    def price_insights(self, trip: TripConfig) -> PriceInsights | None:
        """Return the last cached Google price context for the trip, if any."""
        return self._insights.get(self._cache_key(trip))

    @staticmethod
    def _cache_key(trip: TripConfig) -> str:
        return "|".join(
            [
                str(trip.origin).upper(),
                str(trip.destination).upper(),
                trip.date_from.isoformat(),
                trip.return_from.isoformat() if trip.return_from else "",
                str(trip.passengers),
                trip.seat_class,
                trip.currency,
                str(trip.max_stops),
            ]
        )

    async def _search_fresh(self, trip: TripConfig) -> tuple[list[FlightOffer], PriceInsights | None]:
        await self._maybe_refresh_usage()
        data = await self._request(self._build_params(trip))
        offers = self._parse_flights(data, trip)
        insights = self._parse_price_insights(data)

        if not trip.is_round_trip:
            return offers, insights

        # Round trip: SerpAPI returns each itinerary's OUTBOUND legs plus the
        # combined round-trip price and a departure_token. Fetch the return
        # legs for the cheapest itinerary with a second call and merge.
        cheapest = min(offers, key=lambda o: o.price) if offers else None
        if cheapest is None:
            return [], insights
        token = getattr(cheapest, "_departure_token", None)
        if not token:
            _LOGGER.warning(
                "No departure_token on cheapest outbound for '%s'; "
                "returning outbound-only results",
                trip.name,
            )
            return offers, insights
        return_legs = await self._fetch_return_legs(token, trip)
        if not return_legs:
            _LOGGER.warning(
                "No return legs found for the cheapest outbound of '%s'; "
                "returning outbound-only results",
                trip.name,
            )
            return offers, insights
        return (
            [
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
            ],
            insights,
        )

    async def _fetch_return_legs(self, token: str, trip: TripConfig) -> list[FlightLeg]:
        """Fetch the return legs for a round-trip itinerary via departure_token.

        SerpAPI requires the route context (departure_id/arrival_id/outbound_date
        and, for round trips, return_date) alongside the token; the token itself
        pins the exact itinerary and user so the response echoes that search.
        """
        try:
            data = await self._request(
                {**self._build_params(trip), "departure_token": token}
            )
        except ProviderError as err:
            _LOGGER.warning("SerpAPI return-leg look-up failed: %s", err)
            return []
        item = (data.get("best_flights") or data.get("other_flights") or [{}])[0]
        legs = self._parse_legs(item.get("flights") or [])
        if not legs:
            _LOGGER.warning(
                "SerpAPI departure_token response had no return flights for '%s'",
                trip.name,
            )
            return []
        for leg in legs:
            leg.is_return = True
        return legs

    async def _maybe_refresh_usage(self) -> None:
        """Fetch account quota (no search credit consumed) at most every USAGE_TTL."""
        now = datetime.now(timezone.utc)
        if self._usage_checked is not None and (now - self._usage_checked) < USAGE_TTL:
            return
        self._usage_checked = now
        try:
            data = await self._request(
                {"engine": "account", "api_key": self.api_key}, path="/account"
            )
        except ProviderError as err:
            _LOGGER.warning("Could not refresh SerpAPI quota: %s", err)
            return
        if data.get("this_month_usage") is not None:
            self.used_quota = int(data["this_month_usage"])
        if data.get("total_searches_left") is not None:
            self.quota_remaining = int(data["total_searches_left"])
        elif data.get("plan_searches_left") is not None:
            self.quota_remaining = int(data["plan_searches_left"])
        if data.get("searches_per_month") is not None:
            self.quota_per_month = int(data["searches_per_month"])

    async def _request(
        self, params: dict, *, max_attempts: int = MAX_ATTEMPTS, path: str = SEARCH_PATH
    ) -> dict:
        try:
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
        except ImportError:
            from homeassistant.helpers.aiohttp_client import (  # type: ignore[no-redef]
                async_get_clientsession,
            )

        session = self.options.get("session") or async_get_clientsession(self.hass)
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            try:
                async with session.get(
                    self.base_url + path,
                    params=params,
                ) as resp:
                    status = resp.status
                    if status in (401, 403):
                        raise ProviderAuthError(
                            f"SerpAPI rejected the API key (HTTP {status})"
                        )
                    if status == 429 or status >= 500:
                        if attempt < max_attempts - 1:
                            delay = 2**attempt + random.uniform(0, 1)
                            _LOGGER.warning(
                                "SerpAPI transient HTTP %s, retrying in %.1fs",
                                status,
                                delay,
                            )
                            await asyncio.sleep(delay)
                            continue
                        if status == 429:
                            raise ProviderRateLimitedError(
                                f"SerpAPI rate limit exceeded (HTTP {status})"
                            )
                        raise ProviderError(
                            f"SerpAPI server error (HTTP {status})"
                        )
                    if status >= 400:
                        raise ProviderError(
                            f"SerpAPI error (HTTP {status}): "
                            f"{(await resp.text())[:500]}"
                        )
                    return await resp.json()
            except (ProviderError, ProviderAuthError, ProviderRateLimitedError):
                raise
            except ClientError as err:
                last_error = err
                if attempt < max_attempts - 1:
                    delay = 2**attempt + random.uniform(0, 1)
                    _LOGGER.warning(
                        "SerpAPI request failed (%s), retrying in %.1fs",
                        err,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
        raise ProviderError(
            f"Request to SerpAPI failed: {last_error or 'transient HTTP error'}"
        )

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
            "departure_id": coerce_code(trip.origin),
            "arrival_id": coerce_code(trip.destination),
            "outbound_date": self._fmt_date(trip.date_from),
            "adults": trip.passengers,
            "currency": trip.currency,
            "hl": self.hl,
            "gl": self.gl,
            "sort_by": "2",
        }
        # SerpAPI travel_class: 1=economy, 2=premium economy, 3=business, 4=first
        travel_class = {
            "economy": None,
            "premium_economy": "2",
            "business": "3",
            "first": "4",
        }.get(getattr(trip, "seat_class", "economy"))
        if travel_class:
            params["travel_class"] = travel_class
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
        self, data: dict, trip: TripConfig
    ) -> list[FlightOffer]:
        offers: list[FlightOffer] = []
        for item in data.get("best_flights") or []:
            parsed = self._parse_offer(item, trip)
            if parsed is not None:
                offers.append(parsed)
        for item in data.get("other_flights") or []:
            parsed = self._parse_offer(item, trip)
            if parsed is not None:
                offers.append(parsed)
        return offers

    @staticmethod
    def _parse_price_insights(data: dict) -> PriceInsights | None:
        """Parse Google's price context (typical range + historical series)."""
        pi = data.get("price_insights") or {}
        if not pi:
            return None
        history: list[tuple[date, float]] = []
        for point in pi.get("price_history") or []:
            try:
                timestamp, price = point
                history.append(
                    (datetime.fromtimestamp(float(timestamp), timezone.utc).date(), float(price))
                )
            except (TypeError, ValueError, IndexError):
                continue
        try:
            lowest = float(pi["lowest_price"]) if pi.get("lowest_price") is not None else None
        except (TypeError, ValueError):
            lowest = None
        raw_range = pi.get("typical_price_range") or []
        typical_range: tuple[float | None, float | None] | None = None
        if len(raw_range) >= 2:
            try:
                typical_range = (float(raw_range[0]), float(raw_range[1]))
            except (TypeError, ValueError):
                typical_range = None
        if (
            history
            or lowest is not None
            or typical_range is not None
            or pi.get("price_level")
        ):
            return PriceInsights(
                lowest_price=lowest,
                price_level=pi.get("price_level") or None,
                typical_price_range=typical_range,
                history=history,
            )
        return None

    def _parse_offer(self, item: dict, trip: TripConfig) -> FlightOffer | None:
        raw_price = item.get("price")
        try:
            price = float(raw_price)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            _LOGGER.warning("SerpAPI flight without a numeric price skipped")
            return None

        outbound = self._parse_legs(item.get("flights") or [])
        return_legs = self._parse_legs(item.get("return_flights") or [])

        offer = FlightOffer(
            price=price,
            currency=item.get("currency") or trip.currency,
            outbound=outbound,
            return_legs=return_legs,
            deep_link=self._deep_link(trip),
            booking_token=item.get("booking_token"),
            provider=self.name,
            fetched_at=datetime.now(timezone.utc),
        )
        token = item.get("departure_token")
        if token:
            setattr(offer, "_departure_token", token)
        return offer

    def _deep_link(self, trip: TripConfig) -> str:
        """A real Google Flights search URL that mirrors the trip + search."""
        params = {
            "hl": self.hl,
            "gl": self.gl,
            "curr": trip.currency,
            "departure_id": coerce_code(trip.origin),
            "arrival_id": coerce_code(trip.destination),
            "outbound_date": self._fmt_date(trip.date_from),
            "adults": trip.passengers,
            "type": 1 if trip.is_round_trip else 2,
        }
        if trip.is_round_trip and trip.return_from:
            params["return_date"] = self._fmt_date(trip.return_from)
        return "https://www.google.com/travel/flights?" + urlencode(params)

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

    async def validate_credentials(self) -> str | None:
        params = {
            "engine": "google_flights",
            "api_key": self.api_key,
            "departure_id": "LHR",
            "arrival_id": "JFK",
            "outbound_date": self._fmt_date(datetime.now(timezone.utc).date()),
            "type": 2,
            "hl": self.hl,
            "gl": self.gl,
        }
        try:
            await self._request(params)
        except ProviderAuthError as err:
            return str(err)
        except ProviderError as err:
            return str(err)
        return None

    async def resolve_location(self, query: str) -> list[LocationResult]:
        """Resolve a free-text place to concrete selectable codes.

        Uses the bundled OpenFlights dataset first (no quota cost); falls back
        to SerpAPI's ``google_autocomplete`` engine for places the bundled
        dataset does not know (e.g. city-level or non-OpenFlights airports).
        """
        if not query or not query.strip():
            return []
        local = search_locations(query)
        if local:
            return local
        try:
            data = await self._request(
                {
                    "engine": "google_autocomplete",
                    "api_key": self.api_key,
                    "q": query.strip(),
                    "hl": self.hl,
                    "gl": self.gl,
                }
            )
        except ProviderError as err:
            _LOGGER.warning("SerpAPI autocomplete lookup failed: %s", err)
            return []
        results: list[LocationResult] = []
        for suggestion in data.get("suggestions") or []:
            value = str(suggestion.get("value", ""))
            match = re.search(r"\(([A-Z]{3})\)", value)
            if match:
                results.append(
                    LocationResult(
                        code=match.group(1),
                        name=value,
                        location_type=str(suggestion.get("type", "airport")),
                    )
                )
            if len(results) >= 8:
                break
        return results