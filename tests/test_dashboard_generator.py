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
                        "compare_classes": True,
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


SAMPLE_ENTITY_REGISTRY = {"data": {"entities": [
    {"unique_id": "flight_price_tracker_lon_to_jfk_best_price", "entity_id": "sensor.best_price"},
    {"unique_id": "flight_price_tracker_lon_to_jfk_lowest_price", "entity_id": "sensor.lowest_price"},
    {"unique_id": "flight_price_tracker_lon_to_jfk_offers_count", "entity_id": "sensor.offers_count"},
    {"unique_id": "flight_price_tracker_lon_to_jfk_avg_price", "entity_id": "sensor.average_price"},
    {"unique_id": "flight_price_tracker_lon_to_jfk_price_percentile", "entity_id": "sensor.price_percentile"},
    {"unique_id": "flight_price_tracker_lon_to_jfk_typical_price", "entity_id": "sensor.typical_price"},
    {"unique_id": "flight_price_tracker_lon_to_jfk_historically_cheap", "entity_id": "binary_sensor.historically_cheap"},
    {"unique_id": "flight_price_tracker_lon_to_jfk_target_met", "entity_id": "binary_sensor.target_met"},
    {"unique_id": "flight_price_tracker_lon_to_jfk_class_comparison", "entity_id": "sensor.cabin_class_comparison"},
    {"unique_id": "flight_price_tracker_lon_to_ber_best_price", "entity_id": "sensor.best_price_2"},
    {"unique_id": "flight_price_tracker_lon_to_ber_lowest_price", "entity_id": "sensor.lowest_price_2"},
    {"unique_id": "flight_price_tracker_lon_to_ber_offers_count", "entity_id": "sensor.offers_count_2"},
    {"unique_id": "flight_price_tracker_lon_to_ber_avg_price", "entity_id": "sensor.avg_price_2"},
    {"unique_id": "flight_price_tracker_lon_to_ber_price_percentile", "entity_id": "sensor.price_percentile_2"},
    {"unique_id": "flight_price_tracker_lon_to_ber_typical_price", "entity_id": "sensor.typical_price_2"},
    {"unique_id": "flight_price_tracker_lon_to_ber_historically_cheap", "entity_id": "binary_sensor.historically_cheap_2"},
]}}


def _render() -> str:
    tmp = os.path.join(os.path.dirname(__file__), ".sample_entries.json")
    registry = os.path.join(os.path.dirname(__file__), "core.entity_registry")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(SAMPLE_ENTRIES, handle)
    with open(registry, "w", encoding="utf-8") as handle:
        json.dump(SAMPLE_ENTITY_REGISTRY, handle)
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, tmp],
            capture_output=True,
            text=True,
            check=True,
        )
    finally:
        os.remove(tmp)
        os.remove(registry)
    return result.stdout


class TestDashboardGenerator:
    def test_renders_both_trips(self) -> None:
        output = _render()
        assert "sensor.best_price" in output
        assert "sensor.lowest_price" in output
        assert "sensor.offers_count" in output
        assert "sensor.avg_price" in output
        assert "sensor.price_percentile" in output
        assert "sensor.typical_price" in output
        assert "binary_sensor.historically_cheap" in output
        assert "sensor.best_price_2" in output
        assert output.count("heading:") >= 3  # title + two trips

    def test_uses_real_entity_ids_from_registry(self) -> None:
        output = _render()
        assert "sensor.lon_to_jfk_best_price" not in output
        assert "entity: \"sensor.best_price\"" in output

    def test_target_met_conditional(self) -> None:
        output = _render()
        assert "binary_sensor.target_met" in output
        assert "target_met_2" not in output

    def test_class_comparison_conditional(self) -> None:
        output = _render()
        assert "sensor.cabin_class_comparison" in output
        assert "sensor.best_price_2" in output
        assert "cabin_class_comparison_2" not in output

    def test_template_has_no_leftover_tags(self) -> None:
        output = _render()
        assert "{%" not in output
        assert "{{" not in output

    def test_handles_nested_entries_layout(self) -> None:
        nested = {"version": 1, "key": "x", "data": {"entries": SAMPLE_ENTRIES["data"]}}
        tmp = os.path.join(os.path.dirname(__file__), ".sample_entries.json")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(nested, handle)
        try:
            result = subprocess.run(
                [sys.executable, SCRIPT, tmp],
                capture_output=True,
                text=True,
                check=True,
            )
        finally:
            os.remove(tmp)
        assert "sensor.lon_to_jfk_best_price" in result.stdout
        assert "sensor.lon_to_jfk_class_comparison" in result.stdout

    def test_header_documentation(self) -> None:
        with open(TEMPLATE, encoding="utf-8") as handle:
            content = handle.read()
        assert "generate_dashboard.py" in content
