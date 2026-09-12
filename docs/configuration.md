# Configuration

## Adding an entry

1. **Settings → Devices & services → Add integration → Flight Price Tracker.**
2. Choose a provider and paste your API key (or pick Mock).
3. Set up your first trip (see below).
4. Use **Configure** on the integration afterwards to add, edit or remove trips
   and change the scan interval.

Each config entry holds one provider + your trips. The entry name is derived
from the first trip; re-opening **Configure** gives you a menu to **Add
trip**, **Edit trip**, **Remove trip** or change the **Scan interval**.

## Trip fields

| Field | Meaning |
|---|---|
| `name` | Friendly name shown for the device/sensors. Defaults to "origin → destination". |
| `origin` / `destination` | Departure/arrival airport or city. Either an IATA code (e.g. `LON`), a Google entity id (e.g. `/m/01fgz_`), or a city name that is resolved against the bundled airport/city database. |
| `trip_type` | `one_way` or `round_trip`. |
| `date_from` | Departure date (`YYYY-MM-DD`). |
| `date_to` / `return_from` / `return_to` | Legacy range fields retained for compatibility. Trips are priced as **single dates** — the search uses `date_from` (and `return_from` for round trips). |
| `passengers` | Number of travellers (1–9). |
| `max_stops` | Maximum stops allowed (0–3). `0` = nonstop only. |
| `seat_class` | `economy`, `premium_economy`, `business` or `first`. |
| `compare_classes` | Optional. When on, a dedicated `sensor.<trip>_class_comparison` is created. The comparison is **not** run on every poll — use the `flight_price_tracker.refresh_class_comparison` service or the dashboard button to run it when you want (see [Cabin class comparison](#cabin-class-comparison)). |
| `currency` | ISO currency for prices (GBP, EUR, USD…). |
| `target_price` | If set, trigger a target-reached alert when best price drops to or below this value. |
| `notify_on_target` | Fire the event *and* create a persistent notification on target. |
| `cheap_percentile` | 0.05–0.5; the price percentile that counts as "historically cheap" (default 0.25). |
| `notify_on_cheap` | Fire the cheap event *and* notify when a cheap price first appears. |

Trip IDs are derived from origin and destination (`lon_to_jfk`), suffixed with
`_2` etc. when two trips share a route. Up to 25 trips per entry (see
[MAX_TRIPS]).

[MAX_TRIPS]: https://github.com/MJP-76/ha-flight-price-tracker/blob/main/custom_components/flight_price_tracker/const.py## Return trips

Round trips are queried in **two steps**: first the outbound search, then a
second request using the outbound's `departure_token` to fetch the matching
return legs. The returned offer therefore contains both legs and the combined
price. If a returned outbound offer carries no token, it is kept as
outbound-only rather than dropped.

## Scan interval

Default polling is every **24 hours**. You can set 1–168 hours per entry. Each
poll runs the provider search for every trip and updates the sensors and
price history. Use the `flight_price_tracker.refresh` service to force a poll
at any time.

## Options summary

| Option | Default | Range |
|---|---|---|
| Scan interval (hours) | 24 | 1–168 |
| Passengers | 1 | 1–9 |
| Max stops | 2 | 0–3 |
| Seat class | economy | economy / premium_economy / business / first |
| Compare cabin classes | off | on/off |
| Currency | GBP | see [const.py][MAX_TRIPS] |
| Target price | unset | any positive number |
| Cheap percentile | 0.25 | 0.05–0.5 |
| Notify on target | on | on/off |
| Notify on cheap | on | on/off |

## Entities created per trip

Each trip gets a device with sensors and binary sensors. See
[Sensors & entities](sensors.md) for the full table, the attributes each one
exposes, and the events they can drive.

## "Historically cheap" — how it works

Every poll stores that day's lowest price into the trip's rolling history (one
entry per day, kept for up to 365 days). Once at least 7 daily samples exist,
the current price is compared against the distribution:

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

## Google price insights

When the provider search response contains Google's `price_insights` (currently
the SerpAPI provider), the integration captures:

- **typical price range** — Google's estimate of a typical price for the route
  and travel window;
- **price level** — `low`, `typical`, `high` or `unknown`;
- **lowest price** — Google's lowest observed price;
- **hourly history** — recent price samples used by Google.

These are opportunistic: SerpAPI does not return `price_insights` for every
search. When present they are shown on the `typical_price` sensor (see
[Sensors & entities](sensors.md)) and in the dashboard. When absent, that
sensor's state is `unknown` and the integration quietly skips the feature.

## Cabin class comparison

Turning on **Compare cabin classes** for a trip makes the integration able to
search economy, premium economy, business and first on the same route and
dates, so you can see what an upgrade costs or whether a cheaper class exists
than the one you normally book.

The comparison is **manual**: it does not run during normal polling. Instead,
run it when you want (typically before booking):

- **`flight_price_tracker.refresh_class_comparison`** service — refreshes the
  comparison for one trip (`trip_id`) or every enabled trip;
- **"Check cabin classes"** button on the generated dashboard;
- the integration exposes the last result on
  `sensor.<trip>_class_comparison` until the next time you run the service.

**Search budget.** The trip's own class reuses the primary search's result, so
it costs nothing extra. Each additional class costs one search (two for round
trips, because the return legs need a second token call). A one-way trip
therefore uses up to 3 extra searches per run; a round trip up to 6. Check
this against your provider's monthly quota — see [Providers](providers.md).

**Result.** The best price found across all classes is exposed by
`sensor.<trip>_class_comparison`, with `cheapest_class` and a per-class
`prices`/`classes` breakdown in its attributes. Classes whose search failed
(for example a provider error) are skipped rather than reported as £0. Turning
the option off removes the sensor.

## Persistence

Trip state — best/lowest prices, daily price history, price insights and the
last error per trip — is written to
`<config>/.storage/flight_price_tracker.state` (one blob per config entry) and
survives restarts. The sensors also appear in the HA recorder, so you can graph
`best_price`, `lowest_price` and `avg_price` over time with the built-in
history charts.