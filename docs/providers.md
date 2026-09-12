# Providers

Providers are pluggable: the integration never talks to a specific airline
API directly. A provider is a subclass of `FlightSearchProvider` registered
with the `@register_provider` decorator:

```python
from . import FlightSearchProvider, ProviderError, register_provider


@register_provider("mystery_airlines")
class MysteryAirlinesProvider(FlightSearchProvider):
    display_name = "Mystery Airlines"

    async def search(self, trip):
        # trip: TripConfig — dates, passengers, max_stops, currency
        # return: list[FlightOffer]
        ...

    async def resolve_location(self, query):
        # return: list[LocationResult] (code, city, country, name)
        ...

    async def validate_credentials(self):
        # return error string, or None when the key works
        ...
```

## How a provider is picked up

- The provider appears in the config flow automatically.
- HA URLs and `aiohttp` are used **lazily** inside the provider so it can be
  unit-tested without Home Assistant installed.
- Raise `ProviderError`, `ProviderAuthError` or
  `ProviderRateLimitedError` from `providers/__init__.py` for structured
  failure handling (these map to clean `last_error` messages and re-auth
  prompts).

## Built-in providers

| Provider | Source | Notes |
|---|---|---|
| `serpapi` | Google Flights via [SerpAPI](https://serpapi.com) | **Recommended.** Real fares, price insights, quotas reported. |
| `tequila` | Kiwi.com | Needs a developer API key from `https://api.tequila.kiwi.com/v2` |
| `mock` | built-in | Deterministic demo prices; no account needed |

### SerpAPI (`serpapi`)

Uses the `google_flights` engine with your `api_key` passed as a query
parameter, plus `hl`/`gl` for interface language and region.

- **Search** — one call per one-way trip, with `outbound_date`, `type=2`,
  `stops`, `adults`, `seat_class` and `currency`.
- **Round trips** — the outbound response exposes a `departure_token` per
  offer. Return legs are fetched with a **second call** that replays the route
  context (departure/arrival ids, outbound date, return date) plus the token,
  and the returned segments are merged onto the offer as `return_legs`.
  Offers without a token are kept outbound-only.
- **Price insights** — when the search response includes `price_insights`
  (typical price range, price level, lowest price, history), they are parsed
  and exposed on the `typical_price` sensor. Insights are *opportunistic* —
  SerpAPI returns them for some searches but not others; `None` is cached and
  the feature silently skips. See **Troubleshooting** for the common cause.
- **Quota** — each search reports usage via the SerpAPI `/account` endpoint
  (`this_month_usage` / `searches_per_month`); it is surfaced as
  `provider_quota_used` on the `best_price` sensor.
- **Rate limiting** — `429` responses are retried up to 3 times with a
  backoff, then surfaced as `ProviderRateLimitedError`.
- **Auth** — `401`/`403` raise `ProviderAuthError`, which triggers a
  **re-auth** flow in Home Assistant.

**Cost model:** the free tier is ~100–250 searches/month. One daily poll = 1
search per one-way trip, and 2 searches per round trip (outbound + token
call). A round trip polled daily costs ~60 searches/month.

### Tequila (`tequila`)

Queries Kiwi.com's search API at `base_url` (default
`https://api.tequila.kiwi.com/v2`), authenticating with an `apikey` header.
Uses `fly_from`/`fly_to`/`date_from`/`date_to`/`return_from`/`return_to`,
`max_stopovers` and `curr`. Location autocomplete comes from Tequila's
`locations/query` endpoint.

### Mock (`mock`)

Generates deterministic demo prices from a seeded RNG so you can evaluate the
integration end-to-end without any account. Prices evolve smoothly and every
trip gets a stable set of offers across restarts.

## Location handling

The config flow lets you type a **city name** or **airport name** and has a
picker backed by the bundled datasets:

- `airports.json` — OpenFlights airport data
  ([openflights.org/data.html](https://openflights.org/data.html));
- `primary_cities.json` — maps each city name to the IATA code of its main
  airport.

Values that are already a 3-letter code or a Google entity id (`/m/…`)
are passed through untouched; free text is resolved against the datasets
(`locations.py`, kept free of `homeassistant` imports), so a provider that
rejects city names still receives an airport code.

## Writing your own provider

The only required method is `search()`. Keep it pure of Home Assistant
imports and use the module-level `ProviderError` family for failures. Use the
`_trip()` helper and `FakeSession` from `tests/test_serpapi_provider.py` as a
template for testing your provider without Home Assistant — see
[Development](development.md).

To offer the provider to all users of the add-on you would normally upstream
it as a pull request; a private provider can be shipped inside your HA config
directory instead.