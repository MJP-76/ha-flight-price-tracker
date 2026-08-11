"""Kiwi.com Tequila flight search provider.

Endpoint reference (stable, pre-2024 docs; keys issued before the 2024
invite-only change still work against this API):

* Search:  ``GET {base}/v2/search``  -- ``apikey`` header, params
  ``fly_from``, ``fly_to``, ``date_from``/``date_to`` (dd/mm/yyyy),
  ``return_from``/``return_to`` for round trips, ``adults``, ``curr``,
  ``max_stopovers``, ``sort``, ``limit``.
* Locations: ``GET {base}/locations/query`` -- free-text place resolution.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

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

DEFAULT_BASE_URL = "https://api.tequila.kiwi.com"
SEARCH_PATH = "/v2/search"
LOCATIONS_PATH = "/locations/query"


@register_provider
class TequilaProvider(FlightSearchProvider):
    """Search engine across hundreds of airlines/OTAs via Kiwi.com."""

    name = "tequila"
    display_name = "Kiwi.com Tequila"

    def __init__(self, hass, api_key: str = "", **options) -> None:
        super().__init__(hass, api_key=api_key, **options)
        self.base_url = (options.get("base_url") or DEFAULT_BASE_URL).rstrip("/")

    def _build_params(self, trip: TripConfig) -> dict:
        params: dict = {
            "fly_from": trip.origin,
            "fly_to": trip.destination,
            "date_from": self._fmt_date(trip.date_from),
            "date_to": self._fmt_date(trip.date_to),
            "adults": trip.passengers,
            "curr": trip.currency,
            "max_stopovers": trip.max_stops,
            "limit": int(self.options.get("limit", 50)),
            "sort": "price",
        }
        if trip.is_round_trip:
            params["return_from"] = self._fmt_date(trip.return_from)
            params["return_to"] = self._fmt_date(trip.return_to)
        return params

    @staticmethod
    def _fmt_date(value: date | None) -> str | None:
        return value.strftime("%d/%m/%Y") if value else None

    async def _request(self, path: str, params: dict | None = None) -> dict:
        try:
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
        except ImportError:
            from homeassistant.helpers.aiohttp_client import (  # type: ignore[no-redef]
                async_get_clientsession,
            )

        session = self.options.get("session") or async_get_clientsession(self.hass)
        try:
            async with session.get(
                self.base_url + path,
                params=params,
                headers={"apikey": self.api_key, "Accept": "application/json"},
            ) as resp:
                if resp.status in (401, 403):
                    raise ProviderAuthError(
                        f"Tequila API rejected the API key (HTTP {resp.status})"
                    )
                if resp.status == 429:
                    raise ProviderRateLimitedError(
                        "Tequila API rate limit exceeded (HTTP 429)"
                    )
                if resp.status >= 400:
                    raise ProviderError(
                        f"Tequila API error (HTTP {resp.status}): "
                        f"{(await resp.text())[:500]}"
                    )
                return await resp.json()
        except ProviderError:
            raise
        except ClientError as err:
            raise ProviderError(f"Request to Tequila API failed: {err}") from err

    async def search(self, trip: TripConfig) -> list[FlightOffer]:
        data = await self._request(SEARCH_PATH, params=self._build_params(trip))
        items = data.get("data") or []
        offers = [self._parse_offer(item, trip.currency) for item in items]
        return [offer for offer in offers if offer is not None]

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    def _parse_offer(self, item: dict, fallback_currency: str) -> FlightOffer | None:
        raw_price = item.get("price")
        try:
            price = float(raw_price)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            _LOGGER.warning(
                "Tequila offer without a numeric price skipped: %s", item.get("id")
            )
            return None

        route = item.get("route") or []
        outbound = self._parse_legs(route, is_return=False)
        return_legs = self._parse_legs(route, is_return=True)

        # Some responses only tag return segments explicitly; if no plain
        # outbound legs exist, treat untagged segments as the outbound journey.
        if not outbound and return_legs:
            outbound = return_legs
            return_legs = []

        return FlightOffer(
            price=price,
            currency=item.get("currency") or fallback_currency,
            outbound=outbound,
            return_legs=return_legs,
            deep_link=item.get("deep_link"),
            booking_token=item.get("booking_token"),
            provider=self.name,
            fetched_at=datetime.now(timezone.utc),
        )

    def _parse_legs(self, route: list, is_return: bool) -> list[FlightLeg]:
        legs: list[FlightLeg] = []
        for segment in route:
            if bool(segment.get("return")) != is_return:
                continue
            dep = self._parse_datetime(
                segment.get("utc_departure") or segment.get("local_departure")
            )
            arr = self._parse_datetime(
                segment.get("utc_arrival") or segment.get("local_arrival")
            )
            if dep is None or arr is None:
                continue
            legs.append(
                FlightLeg(
                    airline=str(segment.get("airline", "")),
                    flight_number=str(segment.get("flight_no", "")),
                    origin=str(segment.get("flyFrom", "")),
                    destination=str(segment.get("flyTo", "")),
                    departs_at=dep,
                    arrives_at=arr,
                    is_return=is_return,
                )
            )
        return legs

    async def validate_credentials(self) -> str | None:
        try:
            await self._request(LOCATIONS_PATH, params={"term": "London", "limit": 1})
        except ProviderAuthError as err:
            return str(err)
        except ProviderError as err:
            return str(err)
        return None

    async def resolve_location(self, query: str) -> list[LocationResult]:
        data = await self._request(LOCATIONS_PATH, params={"term": query, "limit": 10})
        results: list[LocationResult] = []
        for item in data.get("data") or []:
            code = item.get("code")
            if not code:
                continue
            country = item.get("country") or {}
            results.append(
                LocationResult(
                    code=str(code),
                    name=str(item.get("name") or ""),
                    location_type=str(item.get("type") or "location"),
                    country=str(country.get("name")) if country.get("name") else None,
                )
            )
        return results
