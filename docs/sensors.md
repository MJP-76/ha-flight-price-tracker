# Sensors & entities

Each trip becomes a **device** (named after the trip, manufacturer *Flight
Price Tracker*, model *Trip*) with the entities below.

Entity IDs are derived from the translated entity names, so the first trip's
entities are `sensor.best_price`, `sensor.typical_price`,
`binary_sensor.target_met`, and so on; the second trip's become
`..._2` (e.g. `sensor.best_price_2`). The docs below use the `lon_to_jfk_` trip
prefix only to make multiple trips unambiguous — your actual IDs will differ.
The **unique IDs** always embed the trip (`flight_price_tracker_lon_to_jfk_best_price`),
so entity IDs are stable across restarts.

## Sensors

### `sensor.<trip>_best_price`
Cheapest offer for the trip on the latest poll (monetary, `GBP`…).

| Attribute | Meaning |
|---|---|
| `airlines` | Airlines sorted, e.g. `British Airways` |
| `flight_numbers` | All flight numbers, e.g. `BA 57, BA 56` (outbound + return) |
| `outbound_stops` | Number of stops on the outbound (0 = nonstop) |
| `return_stops` | Stops on the return leg (`null` on one-way) |
| `departure` / `arrival` | First departure and final arrival timestamps |
| `deep_link` | Link to book/see the offer in the provider's UI |
| `currency` | Price currency |
| `provider` | Provider that found the offer (e.g. `serpapi`) |
| `offers_count` | Itineraries returned by the last poll |
| `origin` / `destination` | Route codes/names |
| `max_stops` / `passengers` / `seat_class` | Trip constraints |
| `departure_date` / `return_date` | Trip dates |
| `provider_quota_used` | Searches used this month (SerpAPI) |
| `last_updated` | Timestamp of the last successful poll |

### `sensor.<trip>_lowest_price`
Lowest price recorded since tracking began (persisted across restarts). Its
attributes describe the *offer* that achieved that low (same shape as
`best_price`).

### `sensor.<trip>_offers_count`
How many itineraries the latest poll returned (`counter` state class).

### `sensor.<trip>_avg_price`
Mean of the recorded **daily** prices.

| Attribute | Meaning |
|---|---|
| `history_count` | Daily samples in the rolling history |
| `price_stddev` / `price_min` / `price_max` | Spread of observed daily prices |
| `cheap_threshold` | Price at the configured cheap percentile |
| `cheap_percentile` | Configured percentile (default 0.25) |
| `enough_data` | False until ≥ 7 daily samples exist |

### `sensor.<trip>_price_percentile`
Where today's price sits in the observed distribution, `0–100` % (0 = cheapest
ever). Attributes mirror `avg_price` plus `historically_cheap` and `avg_price`.

### `sensor.<trip>_typical_price`
Midpoint of Google's **typical price range** for the route and travel window
(only present when the provider returns `price_insights`, otherwise
`unknown`).

| Attribute | Meaning |
|---|---|
| `typical_low` / `typical_high` | Google's typical price range |
| `price_level` | `low`, `typical`, `high` or `unknown` |
| `google_lowest_price` | Lowest price Google has observed for the window |
| `google_history_count` | Number of Google price-history samples captured |
| `best_price` | The live best price, for quick comparison |

### `sensor.<trip>_departure_date`
The trip's departure date (`device_class: date`).

### `sensor.<trip>_return_date`
The trip's return date (round trips only).

## Binary sensors

### `binary_sensor.<trip>_historically_cheap`

ON while the current price is at or below the cheap-percentile threshold of
the recorded daily history. See [Configuration](configuration.md).

| Attribute | Meaning |
|---|---|
| `enough_data` | True once ≥ 7 daily samples exist |
| `price_history_count` | Daily samples recorded |
| `cheap_percentile` / `cheap_threshold` | Cheap zone definition |
| `current_percentile` | 0–1 rank of the current price |
| `avg_price` / `best_price` | For context |

### `binary_sensor.<trip>_target_met`

ON while the best price is at or below the trip's `target_price`. Created only
when a target price is set on the trip. Attributes include `target_price` and
the offer details (`deep_link`, `airlines`, `flight_numbers`, …).

## Lifecycle notes

- Sensors appear/update on the **next refresh** after a trip is added or
  changed (the entry reloads and the coordinator re-polls).
- `available` is driven by `coordinator.last_update_success`; historical
  sensors (`lowest_price`, `avg_price`) stay usable from restored state even if
  a poll fails, while `target_met` requires a live update.
- On a provider error (`last_error` attribute) only the live-trip sensors drop
  offline; your recorded history is preserved.
- The integration also logs `provider_quota_used` per trip on the `best_price`
  sensor, which is useful for watching SerpAPI monthly usage.