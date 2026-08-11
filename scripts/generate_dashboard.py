#!/usr/bin/env python3
"""Render the Flight Price Tracker dashboard template with real entity IDs.

Reads Home Assistant's config entries and renders lovelace/flight-tracker.yaml,
printing the finished dashboard YAML to stdout.

Usage:
    python3 scripts/generate_dashboard.py [path/to/core.config_entries] [-o out.yaml]

The config entries file defaults to /config/.storage/core.config_entries (Home
Assistant OS), falling back to $HOME/.homeassistant/.storage/core.config_entries
and $HOME/.config/homeassistant/.storage/core.config_entries.

The template uses a small subset of Jinja2 ({{ var }}, {% for %}, {% if %})
implemented here with the standard library only, so no extra packages are
needed on the machine that runs it. To install the dashboard, save the output
as a raw-YAML dashboard in Settings -> Dashboards.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(REPO_ROOT, "lovelace", "flight-tracker.yaml")

DOMAIN = "flight_price_tracker"

_ENTRY_CANDIDATES = (
    "/config/.storage/core.config_entries",
    os.path.expanduser("~/.homeassistant/.storage/core.config_entries"),
    os.path.expanduser("~/.config/homeassistant/.storage/core.config_entries"),
)

_TOKEN_RE = re.compile(r"(\{\{.*?\}\}|\{%.*?%\})", re.DOTALL)
_VAR_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")
_FOR_RE = re.compile(r"for\s+(\w+)\s+in\s+(\w+)")
_IF_RE = re.compile(r"if\s+(.+)")


def _lookup(scope: dict, path: str):
    """Resolve a dotted path like trip.best_price against the scope."""
    value = scope
    for part in path.split("."):
        part = part.strip()
        if isinstance(value, dict):
            value = value.get(part, "")
        elif hasattr(value, part):
            value = getattr(value, part)
        else:
            return ""
    return value


def _find_block_end(tokens: list[str], start: int) -> int:
    """Index of the tag closing the block opened at tokens[start]."""
    depth = 1
    for i in range(start + 1, len(tokens)):
        if not tokens[i].startswith("{%"):
            continue
        inner = tokens[i].strip("{%}").strip()
        if inner.startswith(("for ", "if ")):
            depth += 1
        elif inner in ("endfor", "endif"):
            depth -= 1
            if depth == 0:
                return i
    raise ValueError(f"Unclosed block: {tokens[start]}")


def _group(regex: re.Pattern, text: str, group: int) -> str:
    match = regex.search(text)
    return match.group(group) if match else ""


def _render(tokens: list[str], scope: dict) -> str:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("{{"):
            out.append(str(_lookup(scope, _group(_VAR_RE, token, 1))))
            i += 1
        elif token.startswith("{%"):
            inner = token.strip("{%}").strip()
            if inner.startswith("for "):
                varname = _group(_FOR_RE, inner, 1)
                iterable = _group(_FOR_RE, inner, 2)
                end = _find_block_end(tokens, i)
                for item in scope.get(iterable, []):
                    out.append(_render(tokens[i + 1 : end], {**scope, varname: item}))
                i = end + 1
            elif inner.startswith("if "):
                cond = _group(_IF_RE, inner, 1).strip()
                end = _find_block_end(tokens, i)
                if _lookup(scope, cond):
                    out.append(_render(tokens[i + 1 : end], scope))
                i = end + 1
            else:
                i += 1
        else:
            out.append(token)
            i += 1
    return "".join(out)


def _trips_from_entries(entries: list[dict]) -> list[dict]:
    trips: list[dict] = []
    for entry in entries:
        if entry.get("domain") != DOMAIN:
            continue
        for trip in entry.get("options", {}).get("trips", []):
            trip_id = trip["id"]
            trips.append(
                {
                    "name": trip.get("name")
                    or f"{trip.get('origin', '')} to {trip.get('destination', '')}",
                    "origin": trip.get("origin", ""),
                    "destination": trip.get("destination", ""),
                    "date_from": trip.get("date_from", ""),
                    "date_to": trip.get("date_to", ""),
                    "return_from": trip.get("return_from") or "",
                    "return_to": trip.get("return_to") or "",
                    "best_price": f"sensor.{trip_id}_best_price",
                    "lowest_price": f"sensor.{trip_id}_lowest_price",
                    "offers_count": f"sensor.{trip_id}_offers_count",
                    "avg_price": f"sensor.{trip_id}_avg_price",
                    "price_percentile": f"sensor.{trip_id}_price_percentile",
                    "historically_cheap": f"binary_sensor.{trip_id}_historically_cheap",
                    "target_met": (
                        f"binary_sensor.{trip_id}_target_met"
                        if trip.get("target_price")
                        else None
                    ),
                }
            )
    return trips


def _find_config_entries(path: str | None) -> str:
    if path:
        if not os.path.exists(path):
            raise SystemExit(f"Not found: {path}")
        return path
    for candidate in _ENTRY_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    raise SystemExit(
        "Could not locate core.config_entries. Pass the path explicitly:\n"
        "  python3 scripts/generate_dashboard.py /path/to/.storage/core.config_entries"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "config_entries",
        nargs="?",
        help="Path to .storage/core.config_entries (auto-detected if omitted)",
    )
    parser.add_argument(
        "-o", "--output", help="Write the dashboard to this file instead of stdout"
    )
    args = parser.parse_args(argv)

    path = _find_config_entries(args.config_entries)
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    entries = data.get("data", []) if isinstance(data, dict) else data

    trips = _trips_from_entries(entries)
    if not trips:
        print(
            f"No '{DOMAIN}' config entries found in {path}.",
            file=sys.stderr,
        )

    with open(TEMPLATE_PATH, encoding="utf-8") as handle:
        template = handle.read()
    rendered = _render(_TOKEN_RE.split(template), {"trips": trips})

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered)
        print(f"Wrote dashboard to {args.output}")
    else:
        sys.stdout.write(rendered)


if __name__ == "__main__":
    main()
