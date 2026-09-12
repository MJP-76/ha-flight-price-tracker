"""Constants for the Flight Price Tracker integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "flight_price_tracker"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

CONF_PROVIDER = "provider"
CONF_API_KEY = "api_key"
CONF_BASE_URL = "base_url"
CONF_HL = "hl"
CONF_GL = "gl"

DEFAULT_HL = "en"
DEFAULT_GL = "uk"

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
CONF_CHEAP_PERCENTILE = "cheap_percentile"
CONF_NOTIFY_ON_CHEAP = "notify_on_cheap"
CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"

DEFAULT_PROVIDER = "tequila"
DEFAULT_PASSENGERS = 1
DEFAULT_MAX_STOPS = 2
DEFAULT_CURRENCY = "GBP"
DEFAULT_SCAN_INTERVAL_HOURS = 24
MIN_SCAN_INTERVAL_HOURS = 1
MAX_SCAN_INTERVAL_HOURS = 168
DEFAULT_CHEAP_PERCENTILE = 0.25
MIN_CHEAP_PERCENTILE = 0.05
MAX_CHEAP_PERCENTILE = 0.5
MIN_CHEAP_SAMPLES = 7
MAX_HISTORY_DAYS = 365

TRIP_TYPE_ONE_WAY = "one_way"
TRIP_TYPE_ROUND_TRIP = "round_trip"

CONF_SEAT_CLASS = "seat_class"
SEAT_CLASS_ECONOMY = "economy"
SEAT_CLASS_PREMIUM_ECONOMY = "premium_economy"
SEAT_CLASS_BUSINESS = "business"
SEAT_CLASS_FIRST = "first"
DEFAULT_SEAT_CLASS = SEAT_CLASS_ECONOMY

SEAT_CLASS_OPTIONS = [
    {"value": SEAT_CLASS_ECONOMY, "label": "Economy"},
    {"value": SEAT_CLASS_PREMIUM_ECONOMY, "label": "Premium economy"},
    {"value": SEAT_CLASS_BUSINESS, "label": "Business"},
    {"value": SEAT_CLASS_FIRST, "label": "First"},
]

SEAT_CLASSES = (
    SEAT_CLASS_ECONOMY,
    SEAT_CLASS_PREMIUM_ECONOMY,
    SEAT_CLASS_BUSINESS,
    SEAT_CLASS_FIRST,
)

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
