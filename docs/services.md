# Services & events

## Services

| Service | What it does |
|---|---|
| `flight_price_tracker.refresh` | Poll all trips immediately. |
| `flight_price_tracker.add_trip` | Add a trip from an automation (all trip fields as attributes). |
| `flight_price_tracker.update_trip` | Update a trip (all trip fields as attributes). |
| `flight_price_tracker.remove_trip` | Remove a trip (all trip fields as attributes). |
| `flight_price_tracker.resolve_location` | Turn a city/airport name into the provider's code. |

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

## Events

| Event | Data |
|---|---|
| `flight_price_tracker_new_low` | `trip_id`, `trip_name`, `price`, `currency`, `stops`, `deep_link` |
| `flight_price_tracker_target_reached` | same as above |
| `flight_price_tracker_historically_cheap` | `trip_id`, `trip_name`, `price`, `currency`, `current_percentile`, `avg_price`, `cheap_threshold`, `price_history_count`, `cheap_percentile` |