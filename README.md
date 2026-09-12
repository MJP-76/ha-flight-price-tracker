# Flight Price Tracker

**Documentation:** [https://MJP-76.github.io/ha-flight-price-tracker/](https://MJP-76.github.io/ha-flight-price-tracker/)

A Home Assistant integration that watches the best price for your trips and
alerts you when it drops to your target. Price sources are pluggable, so the
integration itself does not depend on any single airline API.

- **Trip-based** — each trip is a route with departure and return dates,
  passenger count, seat class and stop tolerance.
- **Provider-agnostic** — add a new price source by dropping in a small Python
  class. Ships with **Google Flights (SerpAPI)**, Kiwi.com **Tequila** and a
  **Mock** provider.
- **Daily polling** — prices are fetched on a configurable interval (1–168 h).
- **Round-trip aware** — return legs are fetched and merged onto each offer, so
  `best_price`, events and dashboards reflect the full journey (`return_legs`,
  `return_stops`, `flight_numbers`).
- **Google price insights** — when the provider returns them, Google's typical
  price range, price level and lowest price for the route/window are exposed on
  a dedicated `typical_price` sensor.
- **Cabin class comparison** — optionally fetch the best price in every cabin
  class (economy, premium economy, business, first) for the same route and
  dates, and expose the cheapest class plus per-class prices on a dedicated
  sensor. Note this uses extra provider searches (see below).
- **Alerting** — fires `flight_price_tracker_new_low`,
  `flight_price_tracker_target_reached` and
  `flight_price_tracker_historically_cheap` events and can raise a persistent
  notification when a trip hits your target price or drops into the cheapest
  percentile of its own observed history.
- **Historically cheap detection** — each poll records the day's best price,
  then compares the current price against that rolling history (up to a year)
  to flag deals with a statistical basis: percentile rank, rolling average,
  threshold and a binary "historically cheap" sensor.
- **State restored** — last known prices, the lowest price ever seen and the
  price history survive restarts.

## Installation

Install through HACS as a custom repository
(`https://github.com/MJP-76/ha-flight-price-tracker`) or copy
`custom_components/flight_price_tracker/` into your `custom_components`
directory and restart Home Assistant.

### Get an API key

The integration ships with three providers:

| Provider | Source | Free tier | Notes |
| -------- | ------ | --------- | ----- |
| **Google Flights (SerpAPI)** | SerpAPI `google_flights` engine | 100–250 searches/month | No credit card required. Sign up at [serpapi.com](https://serpapi.com). |
| **Kiwi.com Tequila** | Kiwi.com API | Depends on key | Keys are invite-only since 2024; existing keys still work. |
| **Mock** | Built-in | Unlimited | Deterministic demo prices for evaluation. |

**Recommended for most users:** the **SerpAPI** provider. The free tier
covers 100–250 searches per month — plenty for daily price tracking of a few
trips. A single poll uses one search per trip, plus one extra search per round
trip to fetch return legs. Sign up at [serpapi.com](https://serpapi.com) to get
your API key.

To add another provider, follow the [Providers](docs/providers.md) guide.

## Setup

1. **Settings → Devices & services → Add integration → Flight Price Tracker.**
2. Choose a provider and paste your API key (or pick Mock).
3. Enter your first trip: origin, destination, departure date (and return date
   for a round trip), passengers, stops, currency and an optional target price.
4. Use **Configure** on the integration afterwards to add, edit or remove trips
   and change the scan interval.

Each trip becomes a **device** with sensors and binary sensors. Entity IDs are
derived from the entity names (first trip: `sensor.best_price`,
`sensor.typical_price`, …); the tables below use a `lon_to_jfk_` trip prefix
only to keep multiple trips unambiguous:

| Entity | Meaning |
| --- | --- |
| `sensor.<trip>_best_price` | Cheapest offer for the trip right now. |
| `sensor.<trip>_lowest_price` | Lowest price seen since setup. |
| `sensor.<trip>_offers_count` | Number of matching offers returned. |
| `sensor.<trip>_avg_price` | Rolling average of the recorded daily prices. |
| `sensor.<trip>_price_percentile` | Percentile (0–100) of the current price within recorded history. |
| `sensor.<trip>_typical_price` | Midpoint of Google's typical price range (when insights are available). |
| `sensor.<trip>_class_comparison` | Cheapest price across cabin classes (when enabled per trip). |
| `sensor.<trip>_departure_date` | The trip's departure date. |
| `sensor.<trip>_return_date` | The trip's return date (round trips only). |
| `binary_sensor.<trip>_historically_cheap` | On when the current price is in the cheapest percentile of recorded history. |
| `binary_sensor.<trip>_target_met` | On when best price is at/below target. |

The `best_price` sensor carries rich attributes: `airlines`,
`flight_numbers`, `outbound_stops`, `return_stops`, `departure`/`arrival`,
`deep_link`, `provider_quota_used` and more. See
[Sensors & entities](docs/sensors.md) for the full reference.

Trip IDs are derived from origin and destination (`lon_to_jfk`), suffixed with
`_2` etc. when two trips share a route. Up to 25 trips per entry.

### Round trips

Round trips are queried in **two steps**: the outbound search, then a second
request using the outbound's `departure_token` to fetch the matching return
legs. The returned offer contains both legs and the combined price.

### Google price insights

When the search response includes `price_insights`, the integration captures
Google's typical price range, price level, lowest price and recent history and
exposes them on the `typical_price` sensor. Insights are *opportunistic* —
SerpAPI returns them for some searches but not others; when absent the sensor
is `unknown` and the feature is skipped silently.

### "Historically cheap" how it works

Every poll stores that day's lowest price into the trip's rolling history
(one entry per day, kept for up to 365 days). Once at least 7 daily samples
exist, the current price is compared against the distribution:

- `avg_price` — mean of the recorded daily prices;
- `price_percentile` — where today's price sits (0% = cheapest ever);
- `cheap_threshold` — the price below which a day counts as "historically
  cheap" (default: the 25th percentile);
- `historically_cheap` — ON while the current price is at or below that
  threshold.

When the price first crosses into the cheap zone, the integration fires the
`flight_price_tracker_historically_cheap` event and (if enabled) raises a
persistent notification, then waits for the price to leave the cheap zone
before alerting again. Set the percentile (`cheap_percentile`, 0.05–0.5) and
`notify_on_cheap` per trip in the options flow.

### Cabin class comparison

Turn on **Compare cabin classes** for a trip to compare economy, premium
economy, business and first on the same route and dates. The comparison is
**manual** — it does not run on every poll. Run it when you want with the
`flight_price_tracker.refresh_class_comparison` service (or the dashboard's
**Check cabin classes** button).

The trip's own class reuses the primary search's result; every other class
costs one extra search (two for round trips). That is up to 3 extra searches
per run for a one-way trip, 6 for a round trip — budget this against your
provider's monthly quota.

The result lives on `sensor.<trip>_class_comparison`:

- state — the cheapest price found across all classes (GBP);
- `cheapest_class` — the class that won;
- `prices` — best price per class (`e.g. {"economy": 1347, "business": 8150}`);
- `classes` — per-class details (airlines, flight numbers, stops, deep link);
- `currency`, `trip_id`, `last_updated`.

Classes whose search failed are skipped rather than reported as £0. Turning
comparison off removes the sensor.

## Services

- `flight_price_tracker.refresh` — poll all trips immediately.
- `flight_price_tracker.refresh_class_comparison` — run the manual cabin-class
  comparison now for trips that have it enabled.
- `flight_price_tracker.add_trip` / `update_trip` / `remove_trip` — manage
  trips from automations (all trip fields as attributes; `update_trip` /
  `remove_trip` take `trip_id`).
- `flight_price_tracker.resolve_location` — turn a city/airport name into the
  provider's code.

Example automation:

```yaml
alias: Notify when New York trip is cheap
trigger:
  - platform: event
    event_type: flight_price_tracker_target_reached
condition: []
action:
  - service: notify.mobile_app_phone
    data:
      title: "Flights to New York"
      message: "{{ trigger.event.data.price }} {{ trigger.event.data.currency }} via {{ trigger.event.data.deep_link }}"
mode: single
```

## Writing a provider

A provider is a subclass of `FlightSearchProvider` registered with the
`@register_provider` decorator:

```python
from . import FlightSearchProvider, ProviderError, register_provider


@register_provider("mystery_airlines")
class MysteryAirlinesProvider(FlightSearchProvider):
    display_name = "Mystery Airlines"

    async def search(self, trip):
        # trip: TripConfig — dates, passengers, max_stops, currency
        # return: list[FlightOffer]
        ...

    async def resolve_location(self, query):
        # return: list[LocationResult] (code, city, country, name)
        ...

    async def validate_credentials(self):
        # return error string, or None when the key works
        ...
```

The provider appears in the config flow automatically. HA URLs and aiohttp are
used lazily inside the provider so it can be unit-tested without Home Assistant
installed. Raise `ProviderError`, `ProviderAuthError` or `RateLimitedError`
from `providers/__init__.py` for structured failure handling.

## Events

| Event | Data |
| --- | --- |
| `flight_price_tracker_new_low` | `trip_id`, `trip_name`, `origin`, `destination`, `price`, `currency`, `stops`, `deep_link` |
| `flight_price_tracker_target_reached` | same as above |
| `flight_price_tracker_historically_cheap` | `trip_id`, `trip_name`, `origin`, `destination`, `price`, `currency`, `stops`, `current_percentile`, `avg_price`, `cheap_threshold`, `price_history_count`, `cheap_percentile` |

## Lovelace dashboard

The repository includes `lovelace/flight-tracker.yaml`, a ready-made dashboard
view. It is written as a Jinja2 template with placeholders per trip; run
`scripts/generate_dashboard.py` after setup to substitute your real entity IDs
and print the YAML for your dashboard. See [Dashboard](docs/dashboard.md) for
the typical-price card and a history-graph example you can add.

## Diagnostics

Use **Settings → Devices & services → the entry → Diagnose** to get the raw
state, including the last error per trip.

## License

MIT — see [LICENSE](LICENSE).