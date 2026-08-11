# Flight Price Tracker

A Home Assistant integration that watches the best price for your trips and
alerts you when it drops to your target. Price sources are pluggable, so the
integration itself does not depend on any single airline API.

- **Trip-based** — each trip is a route with a date window (and optional return
  leg), passenger count and stop tolerance.
- **Provider-agnostic** — add a new price source by dropping in a small Python
  class. Ships with Kiwi.com Tequila and a Mock provider.
- **Daily polling** — prices are fetched on a configurable interval (1–168 h).
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

The **Tequila** provider queries Kiwi.com. New developer keys are invite-only
as of 2024; if you already have one it still works against
`https://api.tequila.kiwi.com/v2`. Without a key, use the **Mock** provider —
it generates deterministic demo prices so you can evaluate the integration
without any API account.

To add another provider, follow the guide below.

## Setup

1. **Settings → Devices & services → Add integration → Flight Price Tracker.**
2. Choose a provider and paste your API key (or pick Mock).
3. Enter your first trip: origin, destination, date window, passengers, stops,
   currency and an optional target price.
4. For a round trip, choose "Round trip" and give the return window.

After setup you get five sensors per trip plus binary sensors for the cheap and
target signals:

| Entity                         | Meaning                                      |
| ------------------------------ | -------------------------------------------- |
| `sensor.lon_to_jfk_best_price` | Cheapest offer for the trip right now.       |
| `sensor.lon_to_jfk_lowest_price` | Lowest price seen since setup.             |
| `sensor.lon_to_jfk_offers_count` | Number of matching offers returned.        |
| `sensor.lon_to_jfk_avg_price` | Rolling average of the recorded daily prices. |
| `sensor.lon_to_jfk_price_percentile` | Percentile (0–100) of the current price within recorded history. |
| `binary_sensor.lon_to_jfk_historically_cheap` | On when the current price is in the cheapest percentile of recorded history. |
| `binary_sensor.lon_to_jfk_target_met` | On when best price is at/below target.  |

Trip IDs are derived from origin and destination (`lon_to_jfk`), suffixed with
`_2` etc. when two trips share a route.

Use **Configure** on the integration to add, edit or remove trips and change
the scan interval.

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

## Services

- `flight_price_tracker.refresh` — poll all trips immediately.
- `flight_price_tracker.add_trip` / `update_trip` / `remove_trip` — manage
  trips from automations (all trip fields as attributes).
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

| Event                                   | Data                                                        |
| --------------------------------------- | ----------------------------------------------------------- |
| `flight_price_tracker_new_low`          | `trip_id`, `trip_name`, `price`, `currency`, `stops`, `deep_link` |
| `flight_price_tracker_target_reached`   | same as above                                               |
| `flight_price_tracker_historically_cheap` | `trip_id`, `trip_name`, `price`, `currency`, `current_percentile`, `avg_price`, `cheap_threshold`, `price_history_count`, `cheap_percentile` |

## Lovelace dashboard

The repository includes `lovelace/flight-tracker.yaml`, a ready-made dashboard
view. It is written as a Jinja2 template with placeholders per trip; run
`scripts/generate_dashboard.py` after setup to substitute your real entity IDs
and print the YAML for your dashboard (see the script header for details).

## Diagnostics

Use **Settings → Devices & services → the entry → Diagnose** to get the raw
state, including the last error per trip.

## License

MIT — see [LICENSE](LICENSE).
