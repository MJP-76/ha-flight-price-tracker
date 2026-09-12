# Services & events

## Services

All services accept an `entry_id` that selects which config entry to act on
(defaults to the first Flight Price Tracker entry when omitted).

### `flight_price_tracker.refresh`
Immediately re-poll every trip in the entry, outside the normal scan interval.

### `flight_price_tracker.add_trip`
Add a trip from an automation. Required: `origin`, `destination`, `date_from`.
Optional: `name`, `trip_type` (`one_way`/`round_trip`), `return_from`,
`passengers`, `max_stops`, `currency`, `seat_class`, `target_price`,
`notify_on_target`, `cheap_percentile`, `notify_on_cheap`. Sensors appear on
the next refresh.

### `flight_price_tracker.update_trip`
Change any field of an existing trip. `trip_id` is required
(e.g. `lon_to_jfk`), then any subset of the add-trip fields.

### `flight_price_tracker.remove_trip`
Remove a trip and its sensors (`trip_id` required).

### `flight_price_tracker.resolve_location`
Turn a city/airport name into the provider's location code.
Returns `{"locations": [...]}` in the service response.

## Example automation

```yaml
alias: Notify when New York trip is cheap
trigger:
  - platform: event
    event_type: flight_price_tracker_target_reached
action:
  - service: notify.mobile_app_phone
    data:
      title: "Flights to New York"
      message: "{{ trigger.event.data.price }} {{ trigger.event.data.currency }} via {{ trigger.event.data.deep_link }}"
mode: single
```

## Events

### `flight_price_tracker_new_low`
A new lowest price has been recorded.

| Field | Meaning |
|---|---|
| `trip_id`, `trip_name` | Trip identity |
| `origin`, `destination` | Route codes/names |
| `price`, `currency` | The new low price |
| `stops` | Total stops of the offer |
| `deep_link` | Link to the offer in the provider's UI |

### `flight_price_tracker_target_reached`
Best price dropped to or below the trip's `target_price`. Same data as `new_low`.
If `notify_on_target` is on, a persistent notification is also created.

### `flight_price_tracker_historically_cheap`
Current price entered the cheapest percentile of the recorded daily history.

| Field | Meaning |
|---|---|
| `trip_id`, `trip_name`, `origin`, `destination` | Trip identity |
| `price`, `currency` | Current best price |
| `stops` | Max stops configured |
| `current_percentile` | 0–1 rank of the current price |
| `avg_price` | Mean of recorded daily prices |
| `cheap_threshold` | Price at the cheap percentile |
| `price_history_count` | Daily samples recorded |
| `cheap_percentile` | Configured percentile (e.g. 0.25) |

## Notification messages

Target and cheap notifications use `persistent_notification` with stable IDs
(`flight_price_tracker_target_<trip_id>` and
`flight_price_tracker_cheap_<trip_id>`), so each is dismissed or updated rather
than stacking duplicates.