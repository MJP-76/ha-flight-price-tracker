"""Tests for the deterministic mock provider."""

from datetime import date

from custom_components.flight_price_tracker.models import TripConfig
from custom_components.flight_price_tracker.providers.mock import MockProvider


def _trip(*, round_trip: bool = False, max_stops: int = 2) -> TripConfig:
    return TripConfig(
        id="lon_to_jfk",
        name="NY",
        origin="LON",
        destination="JFK",
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 5),
        return_from=date(2026, 9, 8) if round_trip else None,
        return_to=date(2026, 9, 12) if round_trip else None,
        max_stops=max_stops,
    )


def _run(trip: TripConfig):
    import asyncio

    return asyncio.run(MockProvider(None).search(trip))


class TestMockProvider:
    def test_deterministic(self) -> None:
        trip = _trip()
        first = _run(trip)
        second = _run(trip)
        assert first[0].price == second[0].price
        assert first[0].outbound[0].flight_number == second[0].outbound[0].flight_number

    def test_currency_and_provider(self) -> None:
        offer = _run(_trip())[0]
        assert offer.currency == "GBP"
        assert offer.provider == "mock"

    def test_stops_within_limit(self) -> None:
        for _ in range(20):
            offer = _run(_trip(max_stops=1))[0]
            assert offer.stops <= 1

    def test_one_way_has_no_return(self) -> None:
        offer = _run(_trip())[0]
        assert offer.return_legs == []
        assert offer.is_round_trip is False

    def test_round_trip_builds_return_legs_and_costs_more(self) -> None:
        one_way = _run(_trip())[0]
        round_trip = _run(_trip(round_trip=True))[0]
        assert round_trip.return_legs
        assert round_trip.is_round_trip is True
        assert round_trip.price > one_way.price

    def test_validates_without_key(self) -> None:
        import asyncio

        assert asyncio.run(MockProvider(None).validate_credentials()) is None
