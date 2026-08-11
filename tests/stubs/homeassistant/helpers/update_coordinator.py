"""Stub for homeassistant.helpers.update_coordinator."""

from datetime import timedelta


class DataUpdateCoordinator:
    """Shape-compatible stand-in used only so modules can be imported."""

    def __class_getitem__(cls, item):
        return cls

    def __init__(
        self, hass, logger, *, name="", update_interval=None, always_update=False
    ):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval or timedelta(hours=24)
        self.always_update = always_update
        self.data = None
        self.last_update_success = True
        self.config_entry = None

    async def _async_setup(self) -> None:
        pass

    async def async_config_entry_first_refresh(self) -> None:
        await self._async_setup()

    async def async_request_refresh(self) -> None:
        pass


class CoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.hass = coordinator.hass

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()
