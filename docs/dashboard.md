# Dashboard

The repository includes `lovelace/flight-tracker.yaml`, a ready-made dashboard
view per trip.

It is written as a **Jinja2 template** with placeholders per trip. After
setup, run the generator to render it with your real trips and entity IDs,
either printing to stdout or writing the finished YAML:

```bash
python3 scripts/generate_dashboard.py
python3 scripts/generate_dashboard.py -o out.yaml
```

The script reads Home Assistant's config entries (defaulting to the OS path,
with `$HOME` fallbacks), so no extra packages are needed. To install the
dashboard, save the output as a **raw-YAML dashboard** in
**Settings → Dashboards**.

!!! tip "Not sure what entities to reference?"

    See [Configuration](configuration.md) for the full per-trip entity table.