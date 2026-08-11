"""Stub for homeassistant.helpers.entity_platform."""

from collections.abc import Callable
from typing import Any

AddEntitiesCallback = Callable[[list[Any]], None]
