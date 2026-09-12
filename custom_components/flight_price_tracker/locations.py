"""Static airport/city lookup used by the config flow picker and for
auto-resolving free-text origins/destinations that providers reject.

Kept deliberately free of ``homeassistant`` imports so it can be unit tested
in isolation.  The bundled ``airports.json`` is OpenFlights data
(https://openflights.org/data.html) and ``primary_cities.json`` maps each city
name to the IATA code of its main airport.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from .models import LocationResult

_LOGGER = logging.getLogger(__name__)

_AIRPORTS_PATH = "airports.json"
_CITIES_PATH = "primary_cities.json"

# A value that SerpAPI / Tequila can already consume unchanged.
_CODE_RE = re.compile(r"^[A-Za-z]{3}$")

# Strip punctuation/extra whitespace before matching.
_NORM_RE = re.compile(r"[^a-z0-9 ]+")


def looks_like_code(value: str) -> bool:
    """True when the value is already a 3-letter code or a /m/ /g/ entity id."""
    text = (value or "").strip()
    if bool(_CODE_RE.fullmatch(text)):
        return True
    return text.startswith(("/m/", "/g/"))


def normalize(value: str) -> str:
    """Lower-case, keep letters/digits/spaces, collapse whitespace."""
    text = (value or "").lower()
    text = " ".join((_NORM_RE.sub("", text)).split())
    return text


@lru_cache(maxsize=1)
def _airports() -> list[list[str]]:
    import os

    path = os.path.join(os.path.dirname(__file__), _AIRPORTS_PATH)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def _cities() -> dict[str, str]:
    import os

    path = os.path.join(os.path.dirname(__file__), _CITIES_PATH)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _by_code() -> dict[str, list[str]]:
    airports = _airports()
    return {
        row[0]: row  # type: ignore[return-value]
        for row in airports
    }


def _city_index() -> dict[str, list[list[str]]]:
    index: dict[str, list[list[str]]] = {}
    for row in _airports():
        index.setdefault(normalize(row[2]), []).append(row)
    return index


def airport_by_code(code: str) -> LocationResult | None:
    """Return the airport/city for an IATA code, or None when unknown."""
    text = code.strip().upper()
    row = _by_code().get(text)
    if row is None:
        return None
    _airport, name, city, country = row
    return LocationResult(
        code=text,
        name=name,
        location_type="airport",
        country=country,
    )


def resolve_location_code(query: str) -> LocationResult | None:
    """Resolve free-text place names into a concrete location code.

    Prefers the city's primary airport via ``primary_cities.json``, then falls
    back to a case-insensitive city lookup.  Returns the best match or None.
    """
    text = normalize(query)
    if not text:
        return None

    cities = _cities()
    candidates = [c for c in cities if c.lower() == text]
    if not candidates:
        # Allow "new york", "new york city", "-city" suffix failures to still
        # match on the canonical city name.
        candidates = [c for c in cities if c.lower() in text or text in c.lower()]
    if candidates:
        code = cities[candidates[0]]
        result = airport_by_code(code)
        if result is not None:
            _LOGGER.debug("Resolved '%s' to '%s'", query, code)
            return result

    # No primary city matched: try a direct city index scan.
    index = _city_index()
    exact = index.get(text)
    if exact:
        desired = _pick_primary(exact)
        return airport_by_code(desired) if desired else None
    return None


def _pick_primary(rows: list[list[str]]) -> str | None:
    """Pick the 'main' airport from a list of rows in the same city."""
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0][0]
    for phrase in ("international", "intl"):
        for row in rows:
            if phrase in row[1].lower():
                return row[0]
    return rows[0][0]


def search_locations(query: str, limit: int = 10) -> list[LocationResult]:
    """Fuzzy search over airports and cities for the config-flow picker.

    Rankings: exact code, exact city, primary city, then substring matches on
    airport/city names.  City hits are described by their primary airport.
    """
    text = normalize(query)
    if not text:
        return []

    results: list[LocationResult] = []
    seen: set[str] = set()

    def add(result: LocationResult | None) -> None:
        if result is None or result.code in seen:
            return
        seen.add(result.code)
        results.append(result)

    # Exact IATA code lookup first (e.g. "LHR", "lhr").
    code_hit = airport_by_code(text)
    if code_hit is not None:
        add(code_hit)

    # Exact/fuzzy city lookup via the primary-city map.
    resolved = resolve_location_code(text)
    add(resolved)

    # Substring scan of airports' city & name fields.
    airports = _airports()
    for iata, name, city, country in airports:
        if len(results) >= limit:
            break
        n_name = normalize(name)
        n_city = normalize(city)
        if text in n_city or text in n_name:
            # Don't duplicate a code we already found through primary lookup.
            if iata in seen:
                continue
            add(
                LocationResult(
                    code=iata,
                    name=name,
                    location_type="airport",
                    country=country,
                )
            )

    # Filter out matches that are clearly wrong countries for a shared city
    # name (e.g. London, Canada when the user means London, UK).  Only kicks in
    # when the primary city lookup found a match.
    primary_country = resolved.country if resolved else None
    if primary_country:
        results = [
            r
            for r in results
            if r is resolved or r.country == primary_country or r.code in (resolved.code,)
        ]

    return results[:limit]


def coerce_code(value: str) -> str:
    """Return a SerpAPI/Tequila-safe code for ``value``.

    Valid codes pass through unchanged; a known city name becomes its primary
    IATA code; anything unresolvable is returned as-is (as an upper-case code
    attempt).
    """
    text = (value or "").strip()
    if not text:
        return ""
    if looks_like_code(text):
        return text.upper()
    result = resolve_location_code(text)
    if result is not None:
        return result.code
    return text.upper()