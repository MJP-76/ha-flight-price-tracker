"""Tests for the SerpAPI Google Flights provider using a fake aiohttp session."""

from datetime import date

import pytest

from custom_components.flight_price_tracker.models import TripConfig
from custom_components.flight_price_tracker.providers import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitedError,
)
from custom_components.flight_price_tracker.providers.serpapi import SerpAPIProvider


class FakeResponse:
    def __init__(self, status: int, payload=None, text: str = "") -> None:
        self.status = status
        self._payload = payload
        self._text = text

    async def json(self):
        return self._payload or {}

    async def text(self) -> str:
        return self._text


_DEFAULT_ACCOUNT = {"this_month_usage": 5, "searches_per_month": 250}


class FakeSession:
    """Fake aiohttp session that returns pre-built responses in order.

    Account-quota calls (engine=account or URL ending with /account) are
    answered automatically without consuming the queue or appearing in
    ``calls``.  When the response queue is exhausted, the last popped
    response is reused (so retry tests work with a single queue entry).
    """

    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[tuple] = []
        self._last: FakeResponse | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    def get(self, url, params=None, headers=None):
        # Auto-serve account calls silently
        if url.endswith("/account") or (params or {}).get("engine") == "account":
            return FakeSession._Context(FakeResponse(200, _DEFAULT_ACCOUNT))
        self.calls.append((url, params, headers))
        if self.responses:
            self._last = self.responses.pop(0)
        return FakeSession._Context(self._last)

    class _Context:
        def __init__(self, response) -> None:
            self.response = response

        async def __aenter__(self):
            return self.response

        async def __aexit__(self, *exc) -> None:
            return None


def _trip(*, round_trip: bool = False, currency: str = "GBP") -> TripConfig:
    return TripConfig(
        id="lon_to_jfk",
        name="NY",
        origin="LON",
        destination="JFK",
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 1),
        return_from=date(2026, 9, 8) if round_trip else None,
        return_to=date(2026, 9, 8) if round_trip else None,
        currency=currency,
    )


def _provider(session: FakeSession) -> SerpAPIProvider:
    return SerpAPIProvider(None, api_key="test-key", session=session)


def _sample_flight() -> dict:
    """A single flight entry as returned by SerpAPI's Google Flights engine."""
    return {
        "flights": [
            {
                "departure_airport": {
                    "name": "Heathrow Airport",
                    "id": "LHR",
                    "time": "2026-09-01 08:00",
                },
                "arrival_airport": {
                    "name": "John F. Kennedy International Airport",
                    "id": "JFK",
                    "time": "2026-09-01 11:00",
                },
                "duration": 480,
                "airline": "British Airways",
                "flight_number": "BA 117",
            }
        ],
        "layovers": [],
        "total_duration": 480,
        "price": 320,
        "type": "One way",
        "booking_token": "abc123",
    }


def _sample_response(*flights: dict) -> dict:
    return {
        "best_flights": list(flights),
        "other_flights": [],
    }


def _sample_response_round_trip() -> dict:
    """Outbound response for a round-trip search (no return flights yet)."""
    return {
        "best_flights": [
            {
                **_sample_flight(),
                "price": 320,
                "departure_token": "dep_token_xyz",
            }
        ],
        "other_flights": [],
    }


def _sample_return_response() -> dict:
    """Response when fetching return flights via departure_token."""
    return {
        "best_flights": [
            {
                "flights": [
                    {
                        "departure_airport": {
                            "name": "John F. Kennedy International Airport",
                            "id": "JFK",
                            "time": "2026-09-08 18:00",
                        },
                        "arrival_airport": {
                            "name": "Heathrow Airport",
                            "id": "LHR",
                            "time": "2026-09-09 06:00",
                        },
                        "duration": 420,
                        "airline": "British Airways",
                        "flight_number": "BA 118",
                    }
                ],
                "layovers": [],
                "price": 280,
                "type": "Return",
            }
        ],
        "other_flights": [],
    }


class TestBuildParams:
    def test_one_way(self) -> None:
        params = _provider(FakeSession([]))._build_params(_trip())
        assert params["engine"] == "google_flights"
        assert params["departure_id"] == "LON"
        assert params["arrival_id"] == "JFK"
        assert params["outbound_date"] == "2026-09-01"
        assert params["type"] == 2
        assert params["adults"] == 1
        assert params["currency"] == "GBP"
        assert params["sort_by"] == "2"
        assert "return_date" not in params

    def test_round_trip(self) -> None:
        params = _provider(FakeSession([]))._build_params(_trip(round_trip=True))
        assert params["type"] == 1
        assert params["return_date"] == "2026-09-08"

    def test_direct_only(self) -> None:
        trip = _trip()
        trip.max_stops = 0
        params = _provider(FakeSession([]))._build_params(trip)
        assert params["stops"] == 1  # nonstop only

    def test_one_stop(self) -> None:
        trip = _trip()
        trip.max_stops = 1
        params = _provider(FakeSession([]))._build_params(trip)
        assert params["stops"] == 2  # 1 stop or fewer

    def test_two_stops(self) -> None:
        trip = _trip()
        trip.max_stops = 2
        params = _provider(FakeSession([]))._build_params(trip)
        assert params["stops"] == 3  # 2 stops or fewer

    def test_any_stops(self) -> None:
        trip = _trip()
        trip.max_stops = 3
        params = _provider(FakeSession([]))._build_params(trip)
        assert "stops" not in params  # any number of stops


class TestParseOffer:
    def test_parses_flight_legs(self) -> None:
        trip = _trip()
        offer = _provider(FakeSession([]))._parse_offer(_sample_flight(), trip)
        assert offer is not None
        assert offer.price == 320
        assert offer.currency == "GBP"
        assert len(offer.outbound) == 1
        assert offer.outbound[0].airline == "British Airways"
        assert offer.outbound[0].flight_number == "BA 117"
        assert offer.outbound[0].origin == "LHR"
        assert offer.outbound[0].destination == "JFK"

    def test_departure_token_stashed(self) -> None:
        trip = _trip()
        item = {**_sample_flight(), "departure_token": "dep_tok_123"}
        offer = _provider(FakeSession([]))._parse_offer(item, trip)
        assert offer is not None
        assert offer._departure_token == "dep_tok_123"

    def test_skips_offer_without_price(self) -> None:
        item = dict(_sample_flight())
        item["price"] = "N/A"
        assert _provider(FakeSession([]))._parse_offer(item, _trip()) is None

    def test_fallback_currency(self) -> None:
        trip = _trip(currency="USD")
        item = dict(_sample_flight())
        item["price"] = 100
        offer = _provider(FakeSession([]))._parse_offer(item, trip)
        assert offer is not None
        assert offer.currency == "USD"


class TestSearch:
    def test_one_way_search(self) -> None:
        session = FakeSession(
            [FakeResponse(200, _sample_response(_sample_flight()))]
        )
        offers = _run_async(_provider(session).search(_trip()))
        assert len(offers) == 1
        assert offers[0].price == 320
        assert offers[0].outbound[0].airline == "British Airways"

    def test_round_trip_merges_flights(self) -> None:
        session = FakeSession(
            [
                FakeResponse(200, _sample_response_round_trip()),
                FakeResponse(200, _sample_return_response()),
            ]
        )
        offers = _run_async(_provider(session).search(_trip(round_trip=True)))
        assert len(offers) == 1
        assert offers[0].price == 320
        assert len(offers[0].outbound) == 1
        assert offers[0].outbound[0].origin == "LHR"
        assert len(offers[0].return_legs) == 1
        assert offers[0].return_legs[0].origin == "JFK"
        assert offers[0].return_legs[0].flight_number == "BA 118"
        # Account calls are hidden from calls; index 1 = departure_token call
        assert len(session.calls) == 2
        _url, params, _headers = session.calls[1]
        assert params["departure_token"] == "dep_token_xyz"

    def test_round_trip_no_departure_token_returns_outbound(self) -> None:
        """When cheapest outbound has no departure_token, return outbound-only."""
        item = _sample_flight()
        item["price"] = 300
        session = FakeSession(
            [FakeResponse(200, _sample_response(item))]
        )
        offers = _run_async(_provider(session).search(_trip(round_trip=True)))
        assert len(offers) == 1
        assert offers[0].price == 300
        assert offers[0].return_legs == []
        # Only the search call (no return-flight follow-up)
        assert len(session.calls) == 1

    def test_auth_error(self) -> None:
        session = FakeSession([FakeResponse(401)])
        with pytest.raises(ProviderAuthError):
            _run_async(_provider(session).search(_trip()))

    def test_rate_limited_error(self) -> None:
        session = FakeSession([FakeResponse(429)])
        with pytest.raises(ProviderRateLimitedError):
            _run_async(_provider(session).search(_trip()))

    def test_server_error(self) -> None:
        session = FakeSession([FakeResponse(500, text="boom")])
        with pytest.raises(ProviderError):
            _run_async(_provider(session).search(_trip()))

    def test_sends_api_key_as_param(self) -> None:
        session = FakeSession(
            [FakeResponse(200, _sample_response(_sample_flight()))]
        )
        _run_async(_provider(session).search(_trip()))
        _url, params, _headers = session.calls[0]
        assert params["api_key"] == "test-key"

    def test_multiple_flights_returns_all(self) -> None:
        flight2 = dict(_sample_flight())
        flight2["price"] = 450
        flight2["flights"][0] = {
            **flight2["flights"][0],
            "flight_number": "VS 3",
            "airline": "Virgin Atlantic",
        }
        session = FakeSession(
            [FakeResponse(200, _sample_response(_sample_flight(), flight2))]
        )
        offers = _run_async(_provider(session).search(_trip()))
        assert len(offers) == 2
        prices = sorted(o.price for o in offers)
        assert prices == [320, 450]


class TestPriceInsights:
    def test_parses_typical_range_and_history(self) -> None:
        data = {
            "best_flights": [],
            "other_flights": [],
            "price_insights": {
                "lowest_price": 320,
                "price_level": "low",
                "typical_price_range": [400, 600],
                "price_history": [[1630454400, 500.0], [1630540800, 480.0]],
            },
        }
        ins = SerpAPIProvider._parse_price_insights(data)
        assert ins is not None
        assert ins.lowest_price == 320
        assert ins.price_level == "low"
        assert ins.typical_price_range == (400.0, 600.0)
        assert len(ins.history) == 2
        assert ins.history[0][1] == 500.0

    def test_none_when_no_insights_key(self) -> None:
        assert SerpAPIProvider._parse_price_insights({"best_flights": []}) is None

    def test_cached_after_search(self) -> None:
        session = FakeSession(
            [FakeResponse(200, _sample_response(_sample_flight()))]
        )
        prov = _provider(session)
        _run_async(prov.search(_trip()))
        # No price_insights in sample response → None cached
        assert prov.price_insights(_trip()) is None


class TestCredentialValidation:
    def test_validate_credentials_ok(self) -> None:
        session = FakeSession([FakeResponse(200, _sample_response())])
        assert _run_async(_provider(session).validate_credentials()) is None

    def test_validate_credentials_auth_error(self) -> None:
        session = FakeSession([FakeResponse(403)])
        error = _run_async(_provider(session).validate_credentials())
        assert error is not None
        assert "API key" in error


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)
