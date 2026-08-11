"""Tests for the pure per-poll update logic (evaluate_update)."""

from datetime import date

from custom_components.flight_price_tracker.models import (
    FlightLeg,
    FlightOffer,
    TripConfig,
    evaluate_update,
)


def _trip(target_price: float | None = 200.0) -> TripConfig:
    return TripConfig(
        id="lon_to_jfk",
        name="New York trip",
        origin="LON",
        destination="JFK",
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 5),
        target_price=target_price,
    )


def _offer(price: float) -> FlightOffer:
    return FlightOffer(
        price=price,
        currency="GBP",
        outbound=[FlightLeg("BA", "BA100", "LON", "JFK", None, None)],
    )


def _run(trip: TripConfig, info: dict, price: float | None = None) -> dict:
    offers = [] if price is None else [_offer(price)]
    return evaluate_update(trip, info, offers)


class TestEvaluateUpdate:
    def test_first_poll_sets_state(self) -> None:
        result = _run(_trip(), {}, price=180)
        info = result["info"]
        assert info["best_price"] == 180
        assert info["lowest_seen"] == 180
        assert info["offers_count"] == 1
        assert info["target_met"] is True
        assert info["last_error"] is None
        assert result["new_low"] is False

    def test_new_low_fires(self) -> None:
        info = _run(_trip(), {}, price=250)["info"]
        result = _run(_trip(), info, price=220)
        assert result["new_low"] is True
        assert result["info"]["lowest_seen"] == 220
        assert result["info"]["best_price"] == 220

    def test_price_rise_keeps_lowest(self) -> None:
        info = _run(_trip(), {}, price=220)["info"]
        result = _run(_trip(), info, price=300)
        assert result["new_low"] is False
        assert result["info"]["lowest_seen"] == 220
        assert result["info"]["best_price"] == 300

    def test_equal_price_is_not_new_low(self) -> None:
        info = _run(_trip(), {}, price=220)["info"]
        result = _run(_trip(), info, price=220)
        assert result["new_low"] is False

    def test_no_offers(self) -> None:
        info = _run(_trip(), {}, price=220)["info"]
        result = _run(_trip(), info, price=None)
        assert result["info"]["best_price"] is None
        assert result["info"]["offers_count"] == 0
        assert result["info"]["target_met"] is False
        assert result["info"]["lowest_seen"] == 220

    def test_first_poll_with_no_offers_no_lowest(self) -> None:
        result = _run(_trip(), {}, price=None)
        assert result["info"]["lowest_seen"] is None
        assert result["info"]["best_price"] is None
        assert result["new_low"] is False

    def test_target_reached_fires_once(self) -> None:
        result = _run(_trip(target_price=200), {}, price=150)
        assert result["fire_target_reached"] is True
        assert result["info"]["target_met"] is True

        again = _run(_trip(target_price=200), result["info"], price=160)
        assert again["fire_target_reached"] is False
        assert again["info"]["target_met"] is True

    def test_target_reached_then_cleared(self) -> None:
        info = _run(_trip(target_price=200), {}, price=150)["info"]
        result = _run(_trip(target_price=200), info, price=210)
        assert result["fire_target_reached"] is False
        assert result["info"]["target_met"] is False

    def test_no_target_never_fires(self) -> None:
        result = _run(_trip(target_price=None), {}, price=10)
        assert result["fire_target_reached"] is False
        assert result["info"]["target_met"] is False

    def test_offer_attributes_present(self) -> None:
        info = _run(_trip(), {}, price=180)["info"]
        assert info["offer"] is not None
        assert info["offer"]["price"] == 180
        assert info["currency"] == "GBP"
        assert info["trip_name"] == "New York trip"
