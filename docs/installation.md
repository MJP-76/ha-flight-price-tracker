# Installation

## HACS (recommended)

1. In HACS, add this repository as a custom repository (category: **Integration**):
   `https://github.com/MJP-76/ha-flight-price-tracker`
2. Install **Flight Price Tracker** and restart Home Assistant.

## Manual

Copy `custom_components/flight_price_tracker/` into your Home Assistant
`config/custom_components/` directory and restart Home Assistant.

## Get an API key

The **Tequila** provider queries Kiwi.com. New developer keys are invite-only
as of 2024; if you already have one it still works against
`https://api.tequila.kiwi.com/v2`.

!!! tip "No API key? Use the Mock provider"

    Without a key, use the **Mock provider** — it generates deterministic demo
    prices so you can evaluate the integration without any API account.

To add another provider, follow the [Providers](providers.md) guide.