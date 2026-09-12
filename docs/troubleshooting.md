# Troubleshooting

## The `typical_price` sensor is `unknown`

`price_insights` from Google (via SerpAPI) is **opportunistic**: SerpAPI
returns it for some route/window searches but not others. An `unknown` state
simply means the latest poll didn't include insights — the integration skips
the feature gracefully. It is common for it to be present one day and absent
the next.

Check:

- the attributes on the sensor (`typical_low`, `typical_high`,
  `google_history_count`);
- whether a newer poll captured it (`sensor.best_price` `last_updated`).

If it's important to you, set the scan interval shorter so there are more
opportunities to catch a poll that includes insights.

## Tracker hits SerpAPI rate limits (`429`, or quota near the cap)

Cost model: **one search per one-way trip, two per round trip**, per poll. The
free tier is ~100–250 searches/month.

- Watch `provider_quota_used` on `sensor.<trip>_best_price`.
- Increase the entry's **scan interval** (default 24 h).
- Reduce the number of round trips, or drop trips you no longer watch.
- `429` responses are retried automatically (up to 3 attempts with backoff)
  before the poll is marked as failed.

## A round trip returns only outbound legs

The integration fetches return legs with a second SerpAPI call keyed by the
outbound's `departure_token`. Offers without a token are kept as outbound-only
rather than dropped — this is a provider limitation, not a bug. Check the
`return_stops` attribute on `sensor.<trip>_best_price`: `null` on one-way
offers, `0` when a return leg is present.

## Home Assistant triggers a re-auth loop

`401`/`403` from SerpAPI raise `ProviderAuthError`; the integration starts a
re-auth flow so you can paste a new key. Verify your key at
[serpapi.com](https://serpapi.com) and check you're not over the monthly
quota.

## Sensors are `unavailable` after a failed poll

Live sensors (`best_price`, `offers_count`, `target_met`) depend on the last
poll's success. Historical values (`lowest_price`, `avg_price`) are served
from restored state and stay available. To see exactly why a poll failed:

1. **Settings → Devices & services → your entry → Diagnose** — the JSON shows
   `trips.<trip_id>.last_error` and the raw trip state.
2. Check the logbook/error log for `flight_price_tracker` entries.

## "Location not found" when adding a trip

The config flow resolves city names against the bundled `airports.json` /
`primary_cities.json`. If your city isn't in the picker:

- use the **3-letter IATA code** of a nearby airport instead (the integration
  passes 3-letter codes through untouched), or
- use a Google entity id (`/m/…`) if you know it for the SerpAPI provider.

## Prices haven't changed in a while

The default scan interval is **24 h**, so prices only update once a day. Use
the `flight_price_tracker.refresh` service or the dashboard refresh button to
force a poll. Some providers also cache; prices are market-driven, so a real
fare can simply not have moved.

## After updating, something looks different

The integration targets the newest Home Assistant. If a config stopped working
after an update, check the Home Assistant **Release notes / breaking changes**
for the version you moved to, and compare against the integration changelog
in [Releases](https://github.com/MJP-76/ha-flight-price-tracker/releases).