"""Tests for the pure per-poll update logic (evaluate_update)."""

from datetime import date

from custom_components.flight_price_tracker.models import (
    FlightLeg,
    FlightOffer,
    TripConfig,
    evaluate_update,
)


def _trip(target_price: float | None = 200.0, **kwargs) -> TripConfig:
    return TripConfig(
        id="lon_to_jfk",
        name="New York trip",
        origin="LON",
        destination="JFK",
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 5),
        target_price=target_price,
        **kwargs,
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


def _history(*prices: float) -> list[dict]:
    return [{"date": f"2026-0{m + 1:02d}-01", "price": price} for m, price in enumerate(prices)]


class TestHistoricallyCheapEvent:
    def test_fires_when_current_price_in_cheapest_percentile(self) -> None:
        info = {"price_history": _history(100, 150, 200, 250, 300, 350, 400)}
        result = _run(_trip(), info, price=120)
        assert result["fire_historically_cheap"] is True
        assert result["info"]["historically_cheap"] is True
        assert result["info"]["enough_data"] is True

    def test_does_not_fire_without_enough_history(self) -> None:
        info = {"price_history": _history(100, 200)}
        result = _run(_trip(), info, price=80)
        assert result["fire_historically_cheap"] is False
        assert result["info"]["enough_data"] is False

    def test_fires_only_once_until_not_cheap_again(self) -> None:
        info = {"price_history": _history(100, 150, 200, 250, 300, 350, 400)}
        first = _run(_trip(), info, price=120)
        assert first["fire_historically_cheap"] is True

        again = _run(_trip(), first["info"], price=140)
        assert again["fire_historically_cheap"] is False
        assert again["info"]["historically_cheap"] is True

        cleared = _run(_trip(), first["info"], price=380)
        assert cleared["fire_historically_cheap"] is False
        assert cleared["info"]["historically_cheap"] is False

        refired = _run(_trip(), cleared["info"], price=120)
        assert refired["fire_historically_cheap"] is True

    def test_trip_with_no_target_still_tracks_cheap(self) -> None:
        info = {"price_history": _history(100, 150, 200, 250, 300, 350, 400)}
        result = _run(_trip(target_price=None), info, price=110)
        assert result["fire_historically_cheap"] is True

    def test_defaults_history_from_info(self) -> None:
        info = {"price_history": _history(100, 150, 200, 250, 300, 350, 400)}
        result = _run(_trip(), info, price=120)
        assert result["info"]["price_history_count"] == 7

    def test_explicit_history_parameter_wins(self) -> None:
        info = {"price_history": _history(400, 400, 400, 400, 400, 400, 400)}
        result = evaluate_update(
            _trip(), info, [_offer(120)], history=_history(100, 150, 200, 250, 300, 350, 400)
        )
        assert result["fire_historically_cheap"] is True
        assert result["info"]["price_history_count"] == 7

    def test_cheap_stats_exposed_in_state(self) -> None:
        info = {"price_history": _history(100, 150, 200, 250, 300, 350, 400)}
        result = _run(_trip(), info, price=120)["info"]
        assert result["avg_price"] == 250.0
        assert result["cheap_threshold"] is not None
        assert result["current_percentile"] is not None
        assert result["cheap_percentile"] == 0.25
        assert result["price_min"] == 100.0
        assert result["price_max"] == 400.0
