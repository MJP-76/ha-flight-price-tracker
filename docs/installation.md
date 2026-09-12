# Installation

## HACS (recommended)

1. In HACS, add this repository as a custom repository (category: **Integration**):
   `https://github.com/MJP-76/ha-flight-price-tracker`
2. Install **Flight Price Tracker** and restart Home Assistant.

## Manual

Copy `custom_components/flight_price_tracker/` into your Home Assistant
`config/custom_components/` directory and restart Home Assistant.

## Get an API key

The integration ships with three providers:

| Provider | Source | Free tier | Notes |
|---|---|---|---|
| **Google Flights (SerpAPI)** | SerpAPI `google_flights` engine | 100–250 searches/month | No credit card required. Sign up at [serpapi.com](https://serpapi.com). |
| **Kiwi.com Tequila** | Kiwi.com API | Depends on key | Developer keys are invite-only as of 2024; existing keys still work against `https://api.tequila.kiwi.com/v2`. |
| **Mock** | Built-in | Unlimited | Deterministic demo prices for evaluation; no account needed. |

**Recommended for most users:** the **SerpAPI** provider. The free tier covers
100–250 searches per month — plenty for daily price tracking of a few trips.
A single poll uses one search per trip, plus one extra search per round trip
to fetch return legs. Sign up at [serpapi.com](https://serpapi.com) to get your
API key.

!!! tip "No API key? Use the Mock provider"

    Without a key, use the **Mock provider** — it generates deterministic demo
    prices so you can evaluate the integration without any API account.

### Provider-specific options

| Option | Applies to | Meaning |
|---|---|---|
| `base_url` | Tequila | Override the API endpoint (default `https://api.tequila.kiwi.com/v2`). |
| `hl` | SerpAPI | Google Flights interface language (default `en`). |
| `gl` | SerpAPI | Google Flights region/domain (default `uk`). |

To add another provider, follow the [Providers](providers.md) guide.

## Updating

HACS will show you when a new release is available. Restart Home Assistant
after installing an update. Breaking-changes information is published in each
[release](https://github.com/MJP-76/ha-flight-price-tracker/releases).