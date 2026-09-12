"""Tests for the FlightPriceCoordinator class-comparison logic."""

from datetime import date

from custom_components.flight_price_tracker.coordinator import FlightPriceCoordinator
from custom_components.flight_price_tracker.models import FlightLeg, FlightOffer, TripConfig
from custom_components.flight_price_tracker.providers import ProviderError


def _offer(price: float) -> FlightOffer:
    return FlightOffer(
        price=price,
        currency="GBP",
        outbound=[FlightLeg("BA", "BA100", "LON", "JFK", None, None)],
        return_legs=[],
    )


class FakeProvider:
    """Provider returning one offer per seat class; raises for ``bad`` classes."""

    def __init__(self, prices: dict[str, float], *, bad: set[str] | None = None) -> None:
        self.prices = prices
        self.bad = bad or set()
        self.searches: list[str] = []

    async def search(self, trip: TripConfig) -> list[FlightOffer]:
        self.searches.append(trip.seat_class)
        if trip.seat_class in self.bad:
            raise ProviderError("provider down")
        return [_offer(self.prices[trip.seat_class])]


def _coordinator(provider: FakeProvider) -> FlightPriceCoordinator:
    coordinator = object.__new__(FlightPriceCoordinator)
    coordinator.provider = provider
    return coordinator


def _trip(*, seat_class: str = "economy") -> TripConfig:
    return TripConfig(
        id="lon_to_jfk",
        name="NY",
        origin="LON",
        destination="JFK",
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 1),
        seat_class=seat_class,
    )


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


class TestAsyncClassComparison:
    def test_reuses_primary_offer_and_fetches_other_classes(self) -> None:
        provider = FakeProvider(
            {"economy": 300, "premium_economy": 500, "business": 1200, "first": 2000}
        )
        coordinator = _coordinator(provider)
        trip = _trip()
        result = _run_async(
            coordinator._async_class_comparison(trip, primary_offer=_offer(300))
        )
        assert result["prices"] == {
            "economy": 300,
            "premium_economy": 500,
            "business": 1200,
            "first": 2000,
        }
        assert result["cheapest_class"] == "economy"
        assert result["cheapest_price"] == 300
        # Own class is never re-searched
        assert provider.searches == ["premium_economy", "business", "first"]

    def test_failed_class_is_skipped(self) -> None:
        provider = FakeProvider(
            {"economy": 300, "premium_economy": 500, "business": 1200, "first": 2000},
            bad={"business"},
        )
        coordinator = _coordinator(provider)
        result = _run_async(
            coordinator._async_class_comparison(_trip(), primary_offer=_offer(300))
        )
        assert result["prices"] == {"economy": 300, "premium_economy": 500, "first": 2000}
        assert "business" not in result["prices"]
        assert result["cheapest_class"] == "economy"

    def test_different_own_class_is_respected(self) -> None:
        provider = FakeProvider(
            {"economy": 300, "premium_economy": 500, "business": 1200, "first": 2000}
        )
        coordinator = _coordinator(provider)
        trip = _trip(seat_class="business")
        result = _run_async(
            coordinator._async_class_comparison(trip, primary_offer=_offer(1200))
        )
        assert "business" not in provider.searches
        assert result["prices"]["business"] == 1200
        assert result["prices"]["economy"] == 300
        assert result["cheapest_class"] == "economy"