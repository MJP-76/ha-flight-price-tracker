# Flight Price Tracker

[![Home Assistant][badge-home-assistant]][home-assistant]
[![Docs][badge-docs]][docs]
[![Release][badge-release]][releases]

A Home Assistant integration that watches the best price for your trips and
alerts you when it drops to your target. Price sources are pluggable, so the
integration itself does not depend on any single airline API.

## What this integration does

- **Trip-based** — each trip is a route with a date window (and optional
  return leg), passenger count and stop tolerance.
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

## Where to go next

| Topic | Page |
|---|---|
| Install and get an API key | [Installation](installation.md) |
| Set up trips and options | [Configuration](configuration.md) |
| Add your own price source | [Providers](providers.md) |
| Services and events you can automate on | [Services & events](services.md) |
| Ready-made Lovelace dashboard | [Dashboard](dashboard.md) |

[badge-home-assistant]: https://img.shields.io/badge/Home%20Assistant-41BDF5?style=flat-square&logo=homeassistant&logoColor=white
[home-assistant]: https://www.home-assistant.io/
[badge-docs]: https://img.shields.io/badge/Docs-MkDocs-41BDF5?style=flat&logo=materialdesignicons&logoColor=white
[docs]: https://MJP-76.github.io/ha-flight-price-tracker/
[badge-release]: https://img.shields.io/github/v/release/MJP-76/ha-flight-price-tracker?style=flat&label=Release
[releases]: https://github.com/MJP-76/ha-flight-price-tracker/releases