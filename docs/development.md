# Development

Everything needed to hack on the integration and run its test suite.

## Repo layout

```
custom_components/flight_price_tracker/
├── __init__.py        # entry setup/unload, provider instantiation, re-auth hook
├── config_flow.py     # UI flow: provider + API key + trips + options
├── const.py           # all constants and defaults
├── coordinator.py     # per-trip polling, events, persistent storage
├── models.py          # pure data models + trip/history/offer logic (no HA imports)
├── sensor.py          # sensor platform (best/lowest/avg/percentile/typical/offers/dates)
├── binary_sensor.py   # historically_cheap + target_met
├── providers/
│   ├── __init__.py    # FlightSearchProvider base + registry + error types
│   ├── serpapi.py     # Google Flights (SerpAPI), two-call round trips, insights, quota
│   ├── tequila.py     # Kiwi.com provider
│   └── mock.py        # deterministic demo provider
├── locations.py       # airport/city → IATA resolution (pure)
├── airports.json      # OpenFlights dataset
├── primary_cities.json# city → main airport IATA
├── services.py        # refresh / add_trip / update_trip / remove_trip / resolve_location
├── diagnostics.py     # Diagnostics payload for HA
├── manifest.json
├── strings.json       # UI + entity translations
└── translations/en.json

tests/
├── test_models.py             # validation, trip dicts, history, cheap analysis
├── test_serpapi_provider.py   # params, offer parsing, round-trip merge, insights, errors
├── test_tequila_provider.py
├── test_mock_provider.py
├── test_evaluate_update.py    # coordinator update logic
├── test_dashboard_generator.py
└── stubs/homeassistant/       # minimal import stubs when HA isn't installed
```

## Architecture principle

The integration is split so that **all logic that can be pure is pure**:

- `models.py` and `locations.py` never import `homeassistant` — they can be
  unit-tested in isolation.
- Providers use HA's `aiohttp` and URL helpers **lazily** at call time, so a
  fake session (see `tests/test_serpapi_provider.py::FakeSession`) is enough
  to test them without HA installed.
- `coordinator.py` keeps event firing and storage thin; the important update
  decisions (`new_low`, `fire_target_reached`, `fire_historically_cheap`)
  live in the pure `evaluate_update()` in `models.py`, which is what
  `test_evaluate_update.py` exercises.

## Running the tests

```bash
pip install pytest
python3 -m pytest tests/ -q
```

`conftest.py` makes the repo root importable and, when Home Assistant is not
installed, prepends `tests/stubs/homeassistant` (a shape-only stub package) so
all pure-logic tests run anywhere. With real HA installed, the stubs are
skipped and the tests run against the real API surface.

The `FakeSession` in `tests/test_serpapi_provider.py`:

- serves queued responses in call order;
- auto-answers the `/account` quota call without consuming the queue or
  recording it in `calls`;
- reuses the last response when the queue is exhausted (so retry tests pass
  with a single `429`/`500` response).

## Lint & compile

The project targets modern Python; run a syntax check on any edited file:

```bash
python3 -m py_compile custom_components/flight_price_tracker/*.py
```

There is no CI lint gate today, but keep imports ordered and avoid runtime
imports in pure modules.

## Releasing

1. Bump `manifest.json` `version`.
2. Run the test suite (above) until green.
3. Commit, tag, push:

   ```bash
   git add -A && git commit -m "vX.Y.Z: <summary>"
   git tag vX.Y.Z
   git push origin main --tags
   ```

4. Create the release notes (HACS users see the version + notes in the UI):

   ```bash
   gh release create vX.Y.Z
   ```

## Docs site

Documentation lives in `docs/` and is published with
[MkDocs Material](https://squidfunk.github.io/mkdocs-material/).

```bash
pip install mkdocs-material
mkdocs serve       # local preview
mkdocs build --strict   # fails on broken links/markup
```

The GitHub Actions workflow (`.github/workflows/`) rebuilds and deploys the
site to GitHub Pages on every push touching `docs/**` or `mkdocs.yml`.

When you change the docs, verify with `mkdocs build --strict` before pushing —
the deploy workflow runs the same check.

## Testing providers without Home Assistant

Copy the pattern from `tests/test_serpapi_provider.py`:

```python
def _trip(*, round_trip=False, currency="GBP"):
    return TripConfig(id="lon_to_jfk", origin="LON", destination="JFK",
                      date_from=date(2026, 9, 1), date_to=date(2026, 9, 1),
                      return_from=date(2026, 9, 8) if round_trip else None,
                      return_to=date(2026, 9, 8) if round_trip else None,
                      currency=currency, ...)

session = FakeSession([FakeResponse(200, sample_payload)])
offers = asyncio.run(provider.search(_trip()))
```

Test both the "several responses in order" flow (round trips = search then
token call) and the error cases (`401`, `429`, `500`).