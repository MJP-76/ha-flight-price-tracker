# Providers

A provider is a subclass of `FlightSearchProvider` registered with the
`@register_provider` decorator:

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
- Raise `ProviderError`, `ProviderAuthError` or `RateLimitedError` from
  `providers/__init__.py` for structured failure handling.

## Ships with

| Provider | Source | Notes |
|---|---|---|
| Tequila | Kiwi.com | Needs a developer API key from `https://api.tequila.kiwi.com/v2` |
| Mock | built-in | Deterministic demo prices; no account needed |