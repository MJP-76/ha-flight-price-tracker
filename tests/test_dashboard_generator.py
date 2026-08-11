"""Tests for the Lovelace dashboard generator."""

import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "generate_dashboard.py")
TEMPLATE = os.path.join(REPO_ROOT, "lovelace", "flight-tracker.yaml")

SAMPLE_ENTRIES = {
    "version": 1,
    "data": [
        {
            "entry_id": "abc123",
            "domain": "flight_price_tracker",
            "data": {"provider": "tequila"},
            "options": {
                "trips": [
                    {
                        "id": "lon_to_jfk",
                        "name": "New York",
                        "origin": "LON",
                        "destination": "JFK",
                        "date_from": "2026-09-01",
                        "date_to": "2026-09-05",
                        "return_from": None,
                        "return_to": None,
                        "target_price": 250,
                    },
                    {
                        "id": "lon_to_ber",
                        "name": "Berlin",
                        "origin": "LON",
                        "destination": "BER",
                        "date_from": "2026-10-01",
                        "date_to": "2026-10-04",
                        "return_from": None,
                        "return_to": None,
                        "target_price": None,
                    },
                ]
            },
        }
    ],
}


def _render() -> str:
    tmp = os.path.join(os.path.dirname(__file__), ".sample_entries.json")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(SAMPLE_ENTRIES, handle)
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, tmp],
            capture_output=True,
            text=True,
            check=True,
        )
    finally:
        os.remove(tmp)
    return result.stdout


class TestDashboardGenerator:
    def test_renders_both_trips(self) -> None:
        output = _render()
        assert "sensor.lon_to_jfk_best_price" in output
        assert "sensor.lon_to_jfk_lowest_price" in output
        assert "sensor.lon_to_jfk_offers_count" in output
        assert "sensor.lon_to_ber_best_price" in output
        assert output.count("heading:") >= 3  # title + two trips

    def test_target_met_conditional(self) -> None:
        output = _render()
        assert "binary_sensor.lon_to_jfk_target_met" in output
        assert "binary_sensor.lon_to_ber_target_met" not in output

    def test_template_has_no_leftover_tags(self) -> None:
        output = _render()
        assert "{%" not in output
        assert "{{" not in output

    def test_header_documentation(self) -> None:
        with open(TEMPLATE, encoding="utf-8") as handle:
            content = handle.read()
        assert "generate_dashboard.py" in content
