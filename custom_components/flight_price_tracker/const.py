"""Constants for the Flight Price Tracker integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "flight_price_tracker"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

CONF_PROVIDER = "provider"
CONF_API_KEY = "api_key"
CONF_BASE_URL = "base_url"

CONF_TRIPS = "trips"
CONF_TRIP_NAME = "name"
CONF_ORIGIN = "origin"
CONF_DESTINATION = "destination"
CONF_DATE_FROM = "date_from"
CONF_DATE_TO = "date_to"
CONF_RETURN_FROM = "return_from"
CONF_RETURN_TO = "return_to"
CONF_TRIP_TYPE = "trip_type"
CONF_PASSENGERS = "passengers"
CONF_MAX_STOPS = "max_stops"
CONF_CURRENCY = "currency"
CONF_TARGET_PRICE = "target_price"
CONF_NOTIFY_ON_TARGET = "notify_on_target"
CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"

DEFAULT_PROVIDER = "tequila"
DEFAULT_PASSENGERS = 1
DEFAULT_MAX_STOPS = 2
DEFAULT_CURRENCY = "GBP"
DEFAULT_SCAN_INTERVAL_HOURS = 24
MIN_SCAN_INTERVAL_HOURS = 1
MAX_SCAN_INTERVAL_HOURS = 168

TRIP_TYPE_ONE_WAY = "one_way"
TRIP_TYPE_ROUND_TRIP = "round_trip"

# Currency list offered in the config flow (matches Tequila's supported currencies).
CURRENCIES = [
    "GBP",
    "EUR",
    "USD",
    "AUD",
    "CAD",
    "CHF",
    "DKK",
    "NOK",
    "SEK",
    "PLN",
    "CZK",
    "HUF",
    "INR",
    "AED",
    "HKD",
    "SGD",
    "NZD",
    "ZAR",
    "BRL",
    "MXN",
    "THB",
    "ILS",
    "TRY",
]

# Maximum number of trips allowed per config entry.
MAX_TRIPS = 25
