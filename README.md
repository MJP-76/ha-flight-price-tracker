# Flight Price Tracker

A Home Assistant integration that watches the best price for your trips and
alerts you when it drops to your target. Price sources are pluggable, so the
integration itself does not depend on any single airline API.

- **Trip-based** — each trip is a route with a date window (and optional return
  leg), passenger count and stop tolerance.
- **Provider-agnostic** — add a new price source by dropping in a small Python
  class. Ships with Kiwi.com Tequila and a Mock provider.
- **Daily polling** — prices are fetched on a configurable interval (1–168 h).
- **Alerting** — fires `flight_price_tracker_new_low` and
  `flight_price_tracker_target_reached` events and can raise a persistent
  notification when a trip hits your target price.
- **State restored** — last known prices and the lowest price ever seen survive
  restarts.

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

After setup you get three sensors per trip plus a binary sensor when a target
is set:

| Entity                         | Meaning                                      |
| ------------------------------ | -------------------------------------------- |
| `sensor.lon_to_jfk_best_price` | Cheapest offer for the trip right now.       |
| `sensor.lon_to_jfk_lowest_price` | Lowest price seen since setup.             |
| `sensor.lon_to_jfk_offers_count` | Number of matching offers returned.        |
| `binary_sensor.lon_to_jfk_target_met` | On when best price is at/below target.  |

Trip IDs are derived from origin and destination (`lon_to_jfk`), suffixed with
`_2` etc. when two trips share a route.

Use **Configure** on the integration to add, edit or remove trips and change
the scan interval.

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
