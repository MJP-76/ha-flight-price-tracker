# Flight Price Tracker

Track the best price for your trips and get notified when they drop to your target.

- Provider-agnostic: ships with a Kiwi.com Tequila provider and a Mock provider that needs no API key.
- Per-trip sensors for best price, lowest price seen, offer count, rolling average price and price percentile, plus a historically-cheap binary sensor.
- Historically-cheap detection: each poll records the day's price, then flags when the current price sits in the cheapest percentile of its own recorded history, firing `flight_price_tracker_historically_cheap` events and notifications.
- Target-price alerts via `flight_price_tracker_target_reached` events and notifications.
- Polling interval configurable from 1 to 168 hours, with a manual refresh service.
- Fires `flight_price_tracker_new_low` events too.
- Prices, lowest-seen state and the price history survive Home Assistant restarts.

Requires Home Assistant 2024.1 or newer.
