# Configuration

## Adding a trip

1. **Settings → Devices & services → Add integration → Flight Price Tracker.**
2. Choose a provider and paste your API key (or pick Mock).
3. Enter your first trip: origin, destination, date window, passengers, stops,
   currency and an optional target price.
4. For a round trip, choose "Round trip" and give the return window.

Use **Configure** on the integration afterwards to add, edit or remove trips
and change the scan interval.

## Entities created per trip

After setup you get five sensors per trip plus binary sensors for the cheap
and target signals. Trip IDs are derived from origin and destination
(`lon_to_jfk`), suffixed with `_2` etc. when two trips share a route.

| Entity | Meaning |
|---|---|
| `sensor.lon_to_jfk_best_price` | Cheapest offer for the trip right now. |
| `sensor.lon_to_jfk_lowest_price` | Lowest price seen since setup. |
| `sensor.lon_to_jfk_offers_count` | Number of matching offers returned. |
| `sensor.lon_to_jfk_avg_price` | Rolling average of the recorded daily prices. |
| `sensor.lon_to_jfk_price_percentile` | Percentile (0–100) of the current price within recorded history. |
| `binary_sensor.lon_to_jfk_historically_cheap` | On when the current price is in the cheapest percentile of recorded history. |
| `binary_sensor.lon_to_jfk_target_met` | On when best price is at/below target. |

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