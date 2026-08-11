"""Tests for the pure data models and validation logic."""

from datetime import date

from custom_components.flight_price_tracker.models import (
    DEFAULT_CURRENCY,
    DEFAULT_MAX_STOPS,
    DEFAULT_PASSENGERS,
    FlightLeg,
    FlightOffer,
    LocationResult,
    TripConfig,
    best_offer,
    make_trip_id,
    slugify,
    trip_dict_from_form,
    validate_trip_form,
)


def _trip(
    target_price: float | None = None,
    *,
    return_from: date | None = None,
    return_to: date | None = None,
) -> TripConfig:
    return TripConfig(
        id="lon_to_jfk",
        name="New York trip",
        origin="LON",
        destination="JFK",
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 5),
        return_from=return_from,
        return_to=return_to,
        target_price=target_price,
    )


def _offer(price: float, *, legs: int = 1) -> FlightOffer:
    outbound = [FlightLeg("BA", "BA100", "LON", "JFK", None, None)]
    return_legs = (
        [FlightLeg("BA", "BA101", "JFK", "LON", None, None)] if legs > 1 else []
    )
    return FlightOffer(
        price=price, currency="GBP", outbound=outbound, return_legs=return_legs
    )


class TestSlugify:
    def test_simple(self) -> None:
        assert slugify("LON") == "lon"

    def test_spaces_and_punctuation(self) -> None:
        assert slugify("New York-JFK!") == "new_york_jfk"

    def test_leading_trailing_separators(self) -> None:
        assert slugify("--LONDON--") == "london"


class TestMakeTripId:
    def test_unique_ids_for_same_route(self) -> None:
        first = make_trip_id("LON", "JFK", [])
        second = make_trip_id("LON", "JFK", [first])
        assert first == "lon_to_jfk"
        assert second == "lon_to_jfk_2"

    def test_slugified_from_city_names(self) -> None:
        assert (
            make_trip_id("New York", "San Francisco", []) == "new_york_to_san_francisco"
        )


class TestValidateTripForm:
    def test_valid_one_way(self) -> None:
        form = {
            "origin": "LON",
            "destination": "JFK",
            "date_from": "2026-09-01",
            "date_to": "2026-09-05",
        }
        assert validate_trip_form(form) == {}

    def test_missing_origin(self) -> None:
        errors = validate_trip_form(
            {"destination": "JFK", "date_from": "2026-09-01", "date_to": "2026-09-05"}
        )
        assert errors["origin"] == "required"

    def test_same_origin_and_destination(self) -> None:
        errors = validate_trip_form(
            {
                "origin": "LON",
                "destination": "lon",
                "date_from": "2026-09-01",
                "date_to": "2026-09-05",
            }
        )
        assert errors["destination"] == "same_origin_destination"

    def test_date_to_before_from(self) -> None:
        errors = validate_trip_form(
            {
                "origin": "LON",
                "destination": "JFK",
                "date_from": "2026-09-05",
                "date_to": "2026-09-01",
            }
        )
        assert errors["date_to"] == "date_to_before_from"

    def test_bad_dates(self) -> None:
        errors = validate_trip_form(
            {
                "origin": "LON",
                "destination": "JFK",
                "date_from": "not-a-date",
                "date_to": "",
            }
        )
        assert errors["date_from"] == "invalid_date"
        assert errors["date_to"] == "invalid_date"

    def test_round_trip_return_after_departure(self) -> None:
        form = {
            "origin": "LON",
            "destination": "JFK",
            "date_from": "2026-09-01",
            "date_to": "2026-09-05",
            "return_from": "2026-09-04",
            "return_to": "2026-09-10",
        }
        errors = validate_trip_form(form)
        assert errors["return_from"] == "return_before_departure"

    def test_round_trip_valid(self) -> None:
        form = {
            "origin": "LON",
            "destination": "JFK",
            "date_from": "2026-09-01",
            "date_to": "2026-09-05",
            "return_from": "2026-09-08",
            "return_to": "2026-09-12",
        }
        assert validate_trip_form(form) == {}

    def test_passengers_range(self) -> None:
        errors = validate_trip_form(
            {
                "origin": "LON",
                "destination": "JFK",
                "date_from": "2026-09-01",
                "date_to": "2026-09-05",
                "passengers": 0,
            }
        )
        assert errors["passengers"] == "passengers_range"

    def test_max_stops_range(self) -> None:
        errors = validate_trip_form(
            {
                "origin": "LON",
                "destination": "JFK",
                "date_from": "2026-09-01",
                "date_to": "2026-09-05",
                "max_stops": 9,
            }
        )
        assert errors["max_stops"] == "max_stops_range"

    def test_target_price_positive(self) -> None:
        errors = validate_trip_form(
            {
                "origin": "LON",
                "destination": "JFK",
                "date_from": "2026-09-01",
                "date_to": "2026-09-05",
                "target_price": -5,
            }
        )
        assert errors["target_price"] == "target_positive"


class TestTripDictFromForm:
    def test_serialization(self) -> None:
        form = {
            "name": "Work trip",
            "origin": "lon",
            "destination": "New York",
            "date_from": "2026-09-01",
            "date_to": "2026-09-05",
            "passengers": "2",
            "max_stops": "1",
            "currency": "USD",
            "target_price": "250.5",
        }
        trip = trip_dict_from_form(form, trip_id="lon_to_new_york", name="Work trip")
        assert trip["origin"] == "LON"
        assert trip["destination"] == "NEW YORK"
        assert trip["passengers"] == 2
        assert trip["max_stops"] == 1
        assert trip["currency"] == "USD"
        assert trip["target_price"] == 250.5
        assert trip["return_from"] is None

    def test_round_trip_fields(self) -> None:
        form = {
            "origin": "LON",
            "destination": "JFK",
            "date_from": "2026-09-01",
            "date_to": "2026-09-05",
            "return_from": "2026-09-08",
            "return_to": "2026-09-12",
        }
        trip = trip_dict_from_form(form, trip_id="lon_to_jfk", name="NY")
        assert trip["return_from"] == "2026-09-08"
        assert trip["return_to"] == "2026-09-12"


class TestTripConfig:
    def test_roundtrip_to_and_from_dict(self) -> None:
        trip = _trip(
            target_price=200.0,
            return_from=date(2026, 9, 8),
            return_to=date(2026, 9, 12),
        )
        restored = TripConfig.from_dict(trip.to_dict())
        assert restored == trip

    def test_one_way_roundtrip(self) -> None:
        restored = TripConfig.from_dict(_trip().to_dict())
        assert restored.is_round_trip is False
        assert restored.return_from is None

    def test_round_trip_flag(self) -> None:
        assert _trip().is_round_trip is False
        assert (
            _trip(
                return_from=date(2026, 9, 8), return_to=date(2026, 9, 12)
            ).is_round_trip
            is True
        )

    def test_defaults(self) -> None:
        trip = _trip()
        assert trip.passengers == DEFAULT_PASSENGERS
        assert trip.max_stops == DEFAULT_MAX_STOPS
        assert trip.currency == DEFAULT_CURRENCY


class TestOffers:
    def test_best_offer_cheapest(self) -> None:
        offers = [_offer(400), _offer(120), _offer(350)]
        best = best_offer(offers)
        assert best is not None
        assert best.price == 120

    def test_best_offer_empty(self) -> None:
        assert best_offer([]) is None

    def test_stops_properties(self) -> None:
        multi = FlightOffer(
            price=100,
            currency="GBP",
            outbound=[
                FlightLeg("BA", "BA1", "LON", "CDG", None, None),
                FlightLeg("AF", "AF2", "CDG", "JFK", None, None),
            ],
            return_legs=[FlightLeg("AA", "AA3", "JFK", "LON", None, None)],
        )
        assert multi.stops == 1
        assert multi.return_stops == 0
        assert multi.is_round_trip is True

    def test_legs_roundtrip_preserved(self) -> None:
        offer = _offer(300, legs=2)
        assert offer.is_round_trip is True
        assert len(offer.outbound) == 1
        assert len(offer.return_legs) == 1


class TestLocationResult:
    def test_construction(self) -> None:
        location = LocationResult(
            "JFK", "New York John F. Kennedy", "airport", "United States"
        )
        assert location.code == "JFK"
        assert location.country == "United States"
