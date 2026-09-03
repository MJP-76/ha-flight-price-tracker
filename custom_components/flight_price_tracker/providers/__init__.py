"""Pluggable flight price providers.

To add a new provider, subclass :class:`FlightSearchProvider`, decorate it with
:func:`register_provider`, and drop the module into this package. The provider
only needs to translate a :class:`~.models.TripConfig` into a list of
:class:`~.models.FlightOffer`; every other integration concern (polling,
history, sensors, alerting) is provider-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, TypeVar

from ..models import FlightOffer, LocationResult, TripConfig

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

PROVIDERS: dict[str, type[FlightSearchProvider]] = {}

_ProviderT = TypeVar("_ProviderT", bound="FlightSearchProvider")


class ProviderError(Exception):
    """Base error for any provider."""


class ProviderAuthError(ProviderError):
    """The provider rejected the supplied credentials."""


class ProviderRateLimitedError(ProviderError):
    """The provider rate limit was hit."""


def register_provider(cls: type[_ProviderT]) -> type[_ProviderT]:
    """Class decorator registering a provider in the global registry."""
    PROVIDERS[cls.name] = cls
    return cls


class FlightSearchProvider(ABC):
    """Base class for all flight price sources."""

    name: str = "base"
    display_name: str = "Base"

    def __init__(self, hass: HomeAssistant, api_key: str = "", **options: Any) -> None:
        self.hass = hass
        self.api_key = api_key
        self.options = options

    @abstractmethod
    async def search(self, trip: TripConfig) -> list[FlightOffer]:
        """Return the cheapest itineraries found for the trip."""

    @abstractmethod
    async def validate_credentials(self) -> str | None:
        """Return an error message if the API key is invalid, else None."""

    async def resolve_location(self, query: str) -> list[LocationResult]:
        """Resolve a free-text place to selectable codes. Optional."""
        raise ProviderError(f"Provider '{self.name}' does not support location lookup")


def get_provider(
    name: str, hass: HomeAssistant, api_key: str, **options: Any
) -> FlightSearchProvider:
    """Instantiate a provider by registered name."""
    provider_cls = PROVIDERS.get(name)
    if provider_cls is None:
        raise ProviderError(f"Unknown flight provider '{name}'")
    return provider_cls(hass, api_key=api_key, **options)


# Import providers so they register themselves. Importing at the bottom avoids
# circular imports with the registry above.
from . import mock, serpapi, tequila  # noqa: F401
