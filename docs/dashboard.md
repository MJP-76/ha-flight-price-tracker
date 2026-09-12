# Dashboard

The repository includes `lovelace/flight-tracker.yaml`, a skeleton dashboard
view per trip, and `scripts/generate_dashboard.py` to render it with your real
entities.

## Use the built-in generator

`lovelace/flight-tracker.yaml` is a **Jinja2 template** with per-trip
placeholders (name, route, dates, and the `best_price`, `lowest_price`,
`offers_count`, `avg_price`, `price_percentile`, `typical_price` and
`historically_cheap` entities; when a trip has class comparison enabled, a
**Cheapest cabin** tile for `sensor.<trip>_class_comparison` is added
automatically). After setup, run the generator to render it with your trips
and entity IDs:

```bash
python3 scripts/generate_dashboard.py
python3 scripts/generate_dashboard.py -o out.yaml
```

The script reads Home Assistant's config entries (defaulting to the OS path,
with `$HOME` fallbacks), so no extra packages are needed. To install the
dashboard, save the output as a **raw-YAML dashboard** in
**Settings → Dashboards**.

## Adding the "typical price" card manually

The template above shows the live metrics. Add Google's typical-price context
with a Markdown card (using `{{ states(...) }}` in a template card, or a plain
Markdown card if you prefer static text):

```yaml
type: markdown
content: >
  ### Google typical price

  Typical: **{{ states('sensor.typical_price') }} GBP**
  ({{ state_attr('sensor.typical_price', 'typical_low') }} –
  {{ state_attr('sensor.typical_price', 'typical_high') }})
  · level: {{ state_attr('sensor.typical_price', 'price_level') }}
  · Google lowest seen: {{ state_attr('sensor.typical_price', 'google_lowest_price') }}
```

Use this card only as a reminder that the reading is opportunistic: when
SerpAPI hasn't returned `price_insights` for the last poll, the sensor state is
`unknown` and the attribute values are blank.

## Charting your own price history

The integration writes every poll into the HA recorder, so you can graph how
prices move over time with a history-graph card:

```yaml
type: history-graph
title: Price over time
hours_to_show: 168
entities:
  - entity: sensor.lowest_price
    name: Lowest ever
  - entity: sensor.avg_price
    name: 7-day average
  - entity: sensor.best_price
    name: Best now
```

## Showing the cabin class comparison

When a trip has *Compare cabin classes* enabled, its
`sensor.<trip>_class_comparison` carries per-class prices. A template card can
render them as a compact table:

```yaml
type: markdown
content: >
  {% for klass, price in state_attr('sensor.class_comparison', 'prices').items() %}
  - **{{ klass }}**: {{ price }} GBP
  {% endfor %}
  Cheapest: **{{ state_attr('sensor.class_comparison', 'cheapest_class') }}**
```

Or just add a tile: `entity: sensor.class_comparison` (the generator already
does this for you).

## Suggested layout

A per-trip section that combines both:

1. **Heading** with the trip name.
2. **Tiles** for best price, lowest seen and target-met.
3. **Markdown/template card** with the Google typical-price line.
4. **History-graph card** (a week or a month) with `lowest_price`,
   `avg_price` and `best_price`.
5. **Markdown card** with the route, dates, flight numbers and the latest
   `deep_link` so you can jump straight to booking.

!!! tip "Not sure what entities to reference?"

    See [Sensors & entities](sensors.md) for the full per-trip entity table and
    their attributes.