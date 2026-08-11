"""Tests for the Kiwi.com Tequila provider using a fake aiohttp session."""

from datetime import date

import pytest

from custom_components.flight_price_tracker.models import TripConfig
from custom_components.flight_price_tracker.providers import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitedError,
)
from custom_components.flight_price_tracker.providers.tequila import TequilaProvider


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


def _provider(session: FakeSession) -> TequilaProvider:
    return TequilaProvider(None, api_key="test-key", session=session)


def _sample_offer() -> dict:
    return {
        "id": "abc",
        "price": 199.5,
        "currency": "GBP",
        "deep_link": "https://example.com/deep",
        "booking_token": "token-1",
        "route": [
            {
                "flyFrom": "STN",
                "flyTo": "CDG",
                "airline": "FR",
                "flight_no": 100,
                "utc_departure": "2026-09-01T08:00:00Z",
                "utc_arrival": "2026-09-01T10:15:00Z",
                "return": 0,
            },
            {
                "flyFrom": "CDG",
                "flyTo": "JFK",
                "airline": "DL",
                "flight_no": 7,
                "utc_departure": "2026-09-01T12:00:00Z",
                "utc_arrival": "2026-09-01T15:00:00Z",
                "return": 0,
            },
            {
                "flyFrom": "JFK",
                "flyTo": "LON",
                "airline": "BA",
                "flight_no": 112,
                "utc_departure": "2026-09-09T11:00:00Z",
                "utc_arrival": "2026-09-09T22:00:00Z",
                "return": 1,
            },
        ],
    }


class TestBuildParams:
    def test_one_way(self) -> None:
        params = _provider(FakeSession([]))._build_params(_trip())
        assert params["fly_from"] == "LON"
        assert params["fly_to"] == "JFK"
        assert params["date_from"] == "01/09/2026"
        assert params["date_to"] == "05/09/2026"
        assert params["adults"] == 1
        assert params["curr"] == "GBP"
        assert params["sort"] == "price"
        assert "return_from" not in params

    def test_round_trip(self) -> None:
        params = _provider(FakeSession([]))._build_params(_trip(round_trip=True))
        assert params["return_from"] == "08/09/2026"
        assert params["return_to"] == "12/09/2026"


class TestParseOffer:
    def test_parses_outbound_and_return_legs(self) -> None:
        offer = _provider(FakeSession([]))._parse_offer(_sample_offer(), "GBP")
        assert offer is not None
        assert offer.price == 199.5
        assert offer.currency == "GBP"
        assert offer.deep_link == "https://example.com/deep"
        assert len(offer.outbound) == 2
        assert offer.stops == 1
        assert len(offer.return_legs) == 1
        assert offer.return_legs[0].airline == "BA"
        assert offer.return_legs[0].flight_number == "112"

    def test_skips_offer_without_price(self) -> None:
        item = dict(_sample_offer())
        item["price"] = "N/A"
        assert _provider(FakeSession([]))._parse_offer(item, "GBP") is None

    def test_fallback_currency(self) -> None:
        item = dict(_sample_offer())
        item.pop("currency")
        offer = _provider(FakeSession([]))._parse_offer(item, "USD")
        assert offer is not None
        assert offer.currency == "USD"


class TestSearch:
    def test_search_parses_results(self) -> None:
        session = FakeSession([FakeResponse(200, {"data": [_sample_offer()]})])
        offers = _run_async(_provider(session).search(_trip()))
        assert len(offers) == 1
        assert offers[0].price == 199.5
        assert offers[0].stops == 1
        assert offers[0].return_legs[0].airline == "BA"

    def test_auth_error(self) -> None:
        session = FakeSession([FakeResponse(401)])
        provider = _provider(session)
        with pytest.raises(ProviderAuthError):
            _run_async(provider.search(_trip()))

    def test_rate_limited_error(self) -> None:
        session = FakeSession([FakeResponse(429)])
        provider = _provider(session)
        with pytest.raises(ProviderRateLimitedError):
            _run_async(provider.search(_trip()))

    def test_server_error(self) -> None:
        session = FakeSession([FakeResponse(500, text="boom")])
        provider = _provider(session)
        with pytest.raises(ProviderError):
            _run_async(provider.search(_trip()))

    def test_sends_apikey_header(self) -> None:
        session = FakeSession([FakeResponse(200, {"data": []})])
        provider = _provider(session)
        _run_async(provider.search(_trip()))
        _url, _params, headers = session.calls[0]
        assert headers["apikey"] == "test-key"


class TestLocations:
    def test_resolve_location_parses(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    200,
                    {
                        "data": [
                            {
                                "code": "JFK",
                                "name": "John F Kennedy",
                                "type": "airport",
                                "country": {"name": "United States"},
                            }
                        ]
                    },
                )
            ]
        )
        results = _run_async(_provider(session).resolve_location("New York"))
        assert results[0].code == "JFK"
        assert results[0].country == "United States"

    def test_validate_credentials_ok(self) -> None:
        session = FakeSession([FakeResponse(200, {"data": []})])
        assert _run_async(_provider(session).validate_credentials()) is None

    def test_validate_credentials_auth_error(self) -> None:
        session = FakeSession([FakeResponse(403)])
        error = _run_async(_provider(session).validate_credentials())
        assert error is not None
        assert "API key" in error


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)
