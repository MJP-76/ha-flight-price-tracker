# Flight Price Tracker

Track the best price for your trips and get notified when they drop to your target.

- Provider-agnostic: ships with a Kiwi.com Tequila provider and a Mock provider that needs no API key.
- Per-trip sensors for best price, lowest price seen, offer count and a target-met binary sensor.
- Polling interval configurable from 1 to 168 hours, with a manual refresh service.
- Fires `flight_price_tracker_new_low` and `flight_price_tracker_target_reached` events.
- Prices and lowest-seen state survive Home Assistant restarts.

Requires Home Assistant 2024.1 or newer.
