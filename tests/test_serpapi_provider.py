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


class FakeSession:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[tuple] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    def get(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))
        response = self.responses.pop(0)
        return FakeSession._Context(response)

    class _Context:
        def __init__(self, response) -> None:
            self.response = response

        async def __aenter__(self):
            return self.response

        async def __aexit__(self, *exc) -> None:
            return None


def _trip(*, round_trip: bool = False) -> TripConfig:
    return TripConfig(
        id="lon_to_jfk",
        name="NY",
        origin="LON",
        destination="JFK",
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 5),
        return_from=date(2026, 9, 8) if round_trip else None,
        return_to=date(2026, 9, 12) if round_trip else None,
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
        offer = _provider(FakeSession([]))._parse_offer(
            _sample_flight(), "GBP"
        )
        assert offer is not None
        assert offer.price == 320
        assert offer.currency == "GBP"
        assert len(offer.outbound) == 1
        assert offer.outbound[0].airline == "British Airways"
        assert offer.outbound[0].flight_number == "BA 117"
        assert offer.outbound[0].origin == "LHR"
        assert offer.outbound[0].destination == "JFK"

    def test_departure_token_stashed(self) -> None:
        item = {**_sample_flight(), "departure_token": "dep_tok_123"}
        offer = _provider(FakeSession([]))._parse_offer(item, "GBP")
        assert offer is not None
        assert offer._departure_token == "dep_tok_123"

    def test_skips_offer_without_price(self) -> None:
        item = dict(_sample_flight())
        item["price"] = "N/A"
        assert _provider(FakeSession([]))._parse_offer(item, "GBP") is None

    def test_fallback_currency(self) -> None:
        item = dict(_sample_flight())
        item.pop("price", None)
        item["price"] = 100
        offer = _provider(FakeSession([]))._parse_offer(item, "USD")
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
        # Second call should use departure_token
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
        # Only one API call (no return-flight follow-up)
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
