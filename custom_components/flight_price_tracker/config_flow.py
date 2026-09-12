"""Config flow for the Flight Price Tracker integration."""

from __future__ import annotations

import logging
from datetime import date as date_cls
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_CHEAP_PERCENTILE,
    CONF_CURRENCY,
    CONF_DATE_FROM,
    CONF_DESTINATION,
    CONF_GL,
    CONF_HL,
    CONF_MAX_STOPS,
    CONF_NOTIFY_ON_CHEAP,
    CONF_NOTIFY_ON_TARGET,
    CONF_ORIGIN,
    CONF_PASSENGERS,
    CONF_PROVIDER,
    CONF_RETURN_FROM,
    CONF_SCAN_INTERVAL_HOURS,
    CONF_SEAT_CLASS,
    CONF_TARGET_PRICE,
    CONF_TRIP_NAME,
    CONF_TRIP_TYPE,
    CONF_TRIPS,
    CURRENCIES,
    DEFAULT_CHEAP_PERCENTILE,
    DEFAULT_CURRENCY,
    DEFAULT_GL,
    DEFAULT_HL,
    DEFAULT_MAX_STOPS,
    DEFAULT_PASSENGERS,
    DEFAULT_PROVIDER,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DEFAULT_SEAT_CLASS,
    DOMAIN,
    MAX_CHEAP_PERCENTILE,
    MAX_SCAN_INTERVAL_HOURS,
    MAX_TRIPS,
    MIN_CHEAP_PERCENTILE,
    MIN_SCAN_INTERVAL_HOURS,
    SEAT_CLASS_OPTIONS,
    TRIP_TYPE_ONE_WAY,
    TRIP_TYPE_ROUND_TRIP,
)
from .locations import looks_like_code, search_locations
from .models import (
    LocationResult,
    make_trip_id,
    trip_dict_from_form,
    validate_trip_form,
)
from .providers import PROVIDERS, ProviderError, get_provider

_LOGGER = logging.getLogger(__name__)

MAX_STOP_OPTIONS = [
    {"value": "0", "label": "Direct only"},
    {"value": "1", "label": "Up to 1 stop"},
    {"value": "2", "label": "Up to 2 stops"},
    {"value": "3", "label": "Up to 3 stops"},
]

TRIP_TYPE_OPTIONS = [
    {"value": TRIP_TYPE_ONE_WAY, "label": "One way"},
    {"value": TRIP_TYPE_ROUND_TRIP, "label": "Round trip"},
]


def _provider_options() -> list[dict[str, str]]:
    return [
        {"value": name, "label": provider.display_name}
        for name, provider in PROVIDERS.items()
    ]


def _add_required(fields: dict[Any, Any], key: str, default: Any, selector_obj) -> None:
    """Add a required schema field, only passing a default when it exists."""
    if default is None:
        fields[vol.Required(key)] = selector_obj
    else:
        fields[vol.Required(key, default=default)] = selector_obj


def _add_optional(fields: dict[Any, Any], key: str, default: Any, selector_obj) -> None:
    if default is None:
        fields[vol.Optional(key)] = selector_obj
    else:
        fields[vol.Optional(key, default=default)] = selector_obj


def _api_key_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_API_KEY): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            )
        }
    )


def _trip_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    fields: dict[Any, Any] = {
        vol.Optional(
            CONF_TRIP_NAME, default=defaults.get(CONF_TRIP_NAME, "")
        ): selector.TextSelector(),
        vol.Required(
            CONF_ORIGIN, default=defaults.get(CONF_ORIGIN, "")
        ): selector.TextSelector(),
        vol.Required(
            CONF_DESTINATION, default=defaults.get(CONF_DESTINATION, "")
        ): selector.TextSelector(),
        vol.Required(
            CONF_TRIP_TYPE,
            default=defaults.get(CONF_TRIP_TYPE, TRIP_TYPE_ONE_WAY),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(options=TRIP_TYPE_OPTIONS)
        ),
        vol.Required(
            CONF_PASSENGERS,
            default=int(defaults.get(CONF_PASSENGERS, DEFAULT_PASSENGERS)),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=9, step=1, mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_MAX_STOPS,
            default=str(defaults.get(CONF_MAX_STOPS, DEFAULT_MAX_STOPS)),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(options=MAX_STOP_OPTIONS)
        ),
        vol.Required(
            CONF_CURRENCY,
            default=defaults.get(CONF_CURRENCY, DEFAULT_CURRENCY),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(options=list(CURRENCIES))
        ),
        vol.Required(
            CONF_SEAT_CLASS,
            default=defaults.get(CONF_SEAT_CLASS, DEFAULT_SEAT_CLASS),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(options=SEAT_CLASS_OPTIONS)
        ),
        vol.Required(
            CONF_NOTIFY_ON_TARGET,
            default=defaults.get(CONF_NOTIFY_ON_TARGET, True),
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_CHEAP_PERCENTILE,
            default=defaults.get(CONF_CHEAP_PERCENTILE, DEFAULT_CHEAP_PERCENTILE),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=MIN_CHEAP_PERCENTILE,
                max=MAX_CHEAP_PERCENTILE,
                step=0.05,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_NOTIFY_ON_CHEAP,
            default=defaults.get(CONF_NOTIFY_ON_CHEAP, True),
        ): selector.BooleanSelector(),
    }
    _add_required(
        fields, CONF_DATE_FROM, defaults.get(CONF_DATE_FROM), selector.DateSelector()
    )
    _add_optional(
        fields,
        CONF_RETURN_FROM,
        defaults.get(CONF_RETURN_FROM),
        selector.DateSelector(),
    )
    _add_optional(
        fields,
        CONF_TARGET_PRICE,
        defaults.get(CONF_TARGET_PRICE),
        selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, step=1, mode=selector.NumberSelectorMode.BOX
            )
        ),
    )
    return vol.Schema(fields)


def _needs_location_pick(value: Any) -> bool:
    """True when an origin/destination value needs the airport picker."""
    text = str(value or "").strip()
    return bool(text) and not looks_like_code(text)


def _location_pick_schema(options: list[dict[str, str]]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("location"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=options)
            )
        }
    )


async def _location_picker_options(
    hass: HomeAssistant,
    provider: str,
    api_key: str,
    query: str,
    limit: int = 15,
) -> list[dict[str, str]]:
    """Resolve free-text to concrete selectable codes."""
    results: list[LocationResult] = []
    try:
        instance = get_provider(provider, hass, api_key)
        results = await instance.resolve_location(query)
    except Exception:  # noqa: BLE001 - fall back to the static dataset
        results = []
    if not results:
        results = search_locations(query)
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in results[:limit]:
        if result.code in seen:
            continue
        seen.add(result.code)
        label = f"{result.code} — {result.name}"
        if result.country:
            label += f" ({result.country})"
        options.append({"value": result.code, "label": label})
    return options


class _LocationPickerFlow:
    """Shared airport/city picker used by the config and options flows.

    Origin/destination stay free-text in the main trip form.  When a value is
    entered that isn't already a concrete location code, the flow bounces the
    user through :py:meth:`async_step_pick_location` with a list of matching
    airports/cities to confirm the actual code.
    """

    _pick_form: dict[str, Any] = {}
    _pick_field: str = ""
    _pick_options: list[dict[str, str]] = []
    _pick_query: str = ""

    @property
    def _picker_provider(self) -> str:
        raise NotImplementedError

    @property
    def _picker_api_key(self) -> str:
        raise NotImplementedError

    async def _maybe_pick_locations(
        self, form: dict[str, Any]
    ) -> ConfigFlowResult | None:
        """Resolve any free-text location fields, routing through the picker.

        Returns a flow result only when the user must choose; otherwise None
        (validation can then proceed).
        """
        for field in (CONF_ORIGIN, CONF_DESTINATION):
            value = (form.get(field) or "").strip()
            if value and not looks_like_code(value):
                options = await _location_picker_options(
                    self.hass,
                    self._picker_provider,
                    self._picker_api_key,
                    value,
                )
                if not options:
                    return self._location_pick_failed(form, field)
                self._pick_form = dict(form)
                self._pick_field = field
                self._pick_options = options
                self._pick_query = value
                return await self.async_step_pick_location()
        return None

    async def async_step_pick_location(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            form = dict(self._pick_form)
            form[self._pick_field] = user_input["location"]
            pending = await self._maybe_pick_locations(form)
            if pending is not None:
                return pending
            return await self._continue_trip_form(form)
        return self.async_show_form(
            step_id="pick_location",
            data_schema=_location_pick_schema(self._pick_options),
            description_placeholders={"query": self._pick_query},
        )

    async def _continue_trip_form(self, form: dict[str, Any]) -> ConfigFlowResult:
        """Validate the fully-resolved trip form and move along the flow."""
        raise NotImplementedError

    def _location_pick_failed(
        self, form: dict[str, Any], field: str
    ) -> ConfigFlowResult:
        raise NotImplementedError


class FlightPriceTrackerConfigFlow(_LocationPickerFlow, ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Flight Price Tracker."""

    VERSION = 1

    @property
    def _picker_provider(self) -> str:
        return self.provider if hasattr(self, "provider") else ""

    @property
    def _picker_api_key(self) -> str:
        return self.api_key if hasattr(self, "api_key") else ""

    async def _validate_provider_key(self, provider: str, api_key: str) -> str | None:
        try:
            instance = get_provider(provider, self.hass, api_key)
        except ProviderError as err:
            return str(err)
        return await instance.validate_credentials()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        schema_defaults: dict[str, Any] = {}
        if user_input is not None:
            provider = user_input[CONF_PROVIDER]
            api_key = user_input.get(CONF_API_KEY, "")
            if provider != "mock" and not api_key:
                errors[CONF_API_KEY] = "api_key_required"
            elif provider != "mock":
                error = await self._validate_provider_key(provider, api_key)
                if error:
                    errors[CONF_API_KEY] = "invalid_api_key"
                    _LOGGER.warning("Provider validation failed: %s", error)
            if not errors:
                self.provider = provider
                self.api_key = api_key
                return await self.async_step_trip()
            schema_defaults = {CONF_PROVIDER: user_input[CONF_PROVIDER]}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PROVIDER,
                    default=schema_defaults.get(CONF_PROVIDER, DEFAULT_PROVIDER),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_provider_options())
                ),
                vol.Optional(CONF_API_KEY, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_trip(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            picked = await self._maybe_pick_locations(user_input)
            if picked is not None:
                return picked
            errors = validate_trip_form(user_input)
            if not errors:
                self.trip_form = user_input
                return await self.async_step_finish()
        schema = _trip_schema(user_input if user_input else None)
        return self.async_show_form(step_id="trip", data_schema=schema, errors=errors)

    async def _continue_trip_form(self, form: dict[str, Any]) -> ConfigFlowResult:
        errors = validate_trip_form(form)
        if errors:
            return self.async_show_form(
                step_id="trip", data_schema=_trip_schema(form), errors=errors
            )
        self.trip_form = form
        return await self.async_step_finish()

    def _location_pick_failed(
        self, form: dict[str, Any], field: str
    ) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="trip",
            data_schema=_trip_schema(form),
            errors={field: "location_not_found"},
        )

    async def async_step_finish(self) -> ConfigFlowResult:
        form = self.trip_form
        origin = str(form.get(CONF_ORIGIN, "")).strip()
        destination = str(form.get(CONF_DESTINATION, "")).strip()
        name = str(form.get(CONF_TRIP_NAME, "")).strip() or f"{origin} → {destination}"
        trip_id = make_trip_id(origin, destination, [])
        trip = trip_dict_from_form(form, trip_id=trip_id, name=name)
        return self.async_create_entry(
            title=f"Flight tracker: {name}",
            data={CONF_PROVIDER: self.provider, CONF_API_KEY: self.api_key},
            options={
                CONF_TRIPS: [trip],
                CONF_SCAN_INTERVAL_HOURS: DEFAULT_SCAN_INTERVAL_HOURS,
            },
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        provider = entry.data.get(CONF_PROVIDER, DEFAULT_PROVIDER)
        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            error = await self._validate_provider_key(provider, api_key)
            if error:
                errors[CONF_API_KEY] = "invalid_api_key"
            else:
                data = {**entry.data, CONF_API_KEY: api_key}
                self.hass.config_entries.async_update_entry(entry, data=data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
        return self.async_show_form(
            step_id="reauth", data_schema=_api_key_schema(), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        defaults = dict(entry.data)
        if user_input is not None:
            provider = user_input[CONF_PROVIDER]
            api_key = user_input.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY, "")
            if provider != "mock" and not api_key:
                errors[CONF_API_KEY] = "api_key_required"
            elif provider != "mock":
                error = await self._validate_provider_key(provider, api_key)
                if error:
                    errors[CONF_API_KEY] = "invalid_api_key"
            if not errors:
                data = {
                    CONF_PROVIDER: provider,
                    CONF_API_KEY: api_key,
                    CONF_BASE_URL: user_input.get(CONF_BASE_URL)
                    or entry.data.get(CONF_BASE_URL, ""),
                }
                self.hass.config_entries.async_update_entry(entry, data=data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PROVIDER, default=defaults.get(CONF_PROVIDER, DEFAULT_PROVIDER)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_provider_options())
                ),
                vol.Optional(CONF_API_KEY, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(
                    CONF_BASE_URL,
                    default=defaults.get(CONF_BASE_URL, ""),
                ): selector.TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FlightPriceTrackerOptionsFlow(config_entry)


class FlightPriceTrackerOptionsFlow(_LocationPickerFlow, OptionsFlow):
    """Handle options: add/edit/remove trips and provider settings."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.entry = config_entry
        self._pick_mode: str = "add"

    @property
    def _picker_provider(self) -> str:
        return self.entry.data.get(CONF_PROVIDER, DEFAULT_PROVIDER)

    @property
    def _picker_api_key(self) -> str:
        return self.entry.data.get(CONF_API_KEY, "")

    def _trips(self) -> list[dict[str, Any]]:
        return list(self.entry.options.get(CONF_TRIPS, []))

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        trips = self._trips()
        options: list[dict[str, str]] = [
            {"value": "add_trip", "label": "Add a trip"}
        ]
        for trip in trips:
            options.append(
                {"value": f"edit:{trip['id']}", "label": f"Edit: {trip['name']}"}
            )
            options.append(
                {"value": f"remove:{trip['id']}", "label": f"Remove: {trip['name']}"}
            )
        options.append({"value": "settings", "label": "Provider settings"})

        if user_input is not None:
            action = user_input["action"]
            if action == "add_trip":
                return await self.async_step_add_trip()
            if action == "settings":
                return await self.async_step_settings()
            if action.startswith("edit:"):
                self.edit_trip_id = action.split(":", 1)[1]
                return await self.async_step_edit_trip()
            if action.startswith("remove:"):
                self.remove_trip_id = action.split(":", 1)[1]
                return await self.async_step_remove_trip()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def async_step_add_trip(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._pick_mode = "add"
            picked = await self._maybe_pick_locations(user_input)
            if picked is not None:
                return picked
            if len(self._trips()) >= MAX_TRIPS:
                return self.async_abort(reason="max_trips")
            errors = validate_trip_form(user_input)
            if not errors:
                trips = self._trips()
                existing = [trip["id"] for trip in trips]
                origin = str(user_input.get(CONF_ORIGIN, "")).strip()
                destination = str(user_input.get(CONF_DESTINATION, "")).strip()
                name = (
                    str(user_input.get(CONF_TRIP_NAME, "")).strip()
                    or f"{origin} → {destination}"
                )
                trip = trip_dict_from_form(
                    user_input,
                    trip_id=make_trip_id(origin, destination, existing),
                    name=name,
                )
                trips.append(trip)
                await self._update_options({CONF_TRIPS: trips})
                return self.async_abort(reason="trip_added")
        schema = _trip_schema(user_input if user_input else None)
        return self.async_show_form(
            step_id="add_trip", data_schema=schema, errors=errors
        )

    async def _continue_trip_form(self, form: dict[str, Any]) -> ConfigFlowResult:
        """Continue validation/commit after the location picker resolved."""
        errors = validate_trip_form(form)
        if errors:
            step_id = "edit_trip" if self._pick_mode == "edit" else "add_trip"
            return self.async_show_form(
                step_id=step_id, data_schema=_trip_schema(form), errors=errors
            )
        if self._pick_mode == "edit":
            self.trip_form = form
            return await self.async_edit_commit()
        if len(self._trips()) >= MAX_TRIPS:
            return self.async_abort(reason="max_trips")
        trips = self._trips()
        existing = [trip["id"] for trip in trips]
        origin = str(form.get(CONF_ORIGIN, "")).strip()
        destination = str(form.get(CONF_DESTINATION, "")).strip()
        name = (
            str(form.get(CONF_TRIP_NAME, "")).strip()
            or f"{origin} → {destination}"
        )
        trip = trip_dict_from_form(
            form,
            trip_id=make_trip_id(origin, destination, existing),
            name=name,
        )
        trips.append(trip)
        await self._update_options({CONF_TRIPS: trips})
        return self.async_abort(reason="trip_added")

    def _location_pick_failed(
        self, form: dict[str, Any], field: str
    ) -> ConfigFlowResult:
        step_id = "edit_trip" if self._pick_mode == "edit" else "add_trip"
        return self.async_show_form(
            step_id=step_id,
            data_schema=_trip_schema(form),
            errors={field: "location_not_found"},
        )

    async def async_step_edit_trip(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        trips = self._trips()
        trip = next((t for t in trips if t["id"] == self.edit_trip_id), None)
        if trip is None:
            return self.async_abort(reason="trip_missing")
        errors: dict[str, str] = {}
        if user_input is not None:
            self._pick_mode = "edit"
            picked = await self._maybe_pick_locations(user_input)
            if picked is not None:
                return picked
            errors = validate_trip_form(user_input)
            if not errors:
                self.trip_form = user_input
                return await self.async_edit_commit()
        defaults = (
            user_input
            if user_input is not None
            else _trip_defaults(trip)
        )
        return self.async_show_form(
            step_id="edit_trip", data_schema=_trip_schema(defaults), errors=errors
        )

    async def async_edit_commit(self) -> ConfigFlowResult:
        form = self.trip_form
        trips = self._trips()
        trip = next((t for t in trips if t["id"] == self.edit_trip_id), None)
        if trip is None:
            return self.async_abort(reason="trip_missing")
        name = (
            str(form.get(CONF_TRIP_NAME, "")).strip()
            or trip["name"]
        )
        new_trip = trip_dict_from_form(
            form, trip_id=trip["id"], name=name
        )
        trips = [new_trip if t["id"] == trip["id"] else t for t in trips]
        await self._update_options({CONF_TRIPS: trips})
        return self.async_abort(reason="trip_updated")

    async def async_step_remove_trip(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        trips = self._trips()
        trip = next((t for t in trips if t["id"] == self.remove_trip_id), None)
        if trip is None:
            return self.async_abort(reason="trip_missing")
        if user_input is not None:
            trips = [t for t in trips if t["id"] != self.remove_trip_id]
            await self._update_options({CONF_TRIPS: trips})
            return self.async_abort(reason="trip_removed")
        return self.async_show_form(
            step_id="remove_trip",
            data_schema=vol.Schema(
                {vol.Required("confirm", default=True): selector.BooleanSelector()}
            ),
            description_placeholders={"trip_name": trip["name"]},
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self.entry
        current_provider = entry.data.get(CONF_PROVIDER, DEFAULT_PROVIDER)
        scan_default = entry.options.get(
            CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
        )
        base_url_default = entry.data.get(CONF_BASE_URL, "")
        hl_default = entry.data.get(CONF_HL, DEFAULT_HL)
        gl_default = entry.data.get(CONF_GL, DEFAULT_GL)
        if user_input is not None:
            provider = user_input[CONF_PROVIDER]
            api_key = user_input.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY, "")
            if provider != "mock" and not api_key:
                errors[CONF_API_KEY] = "api_key_required"
            elif provider != "mock":
                error = await _validate_key_for(self.hass, provider, api_key)
                if error:
                    errors[CONF_API_KEY] = "invalid_api_key"
            scan = int(user_input[CONF_SCAN_INTERVAL_HOURS])
            if not MIN_SCAN_INTERVAL_HOURS <= scan <= MAX_SCAN_INTERVAL_HOURS:
                errors[CONF_SCAN_INTERVAL_HOURS] = "scan_interval_range"
            if not errors:
                data = {
                    **entry.data,
                    CONF_PROVIDER: provider,
                    CONF_API_KEY: api_key,
                    CONF_BASE_URL: user_input.get(CONF_BASE_URL) or "",
                    CONF_HL: str(user_input.get(CONF_HL) or DEFAULT_HL),
                    CONF_GL: str(user_input.get(CONF_GL) or DEFAULT_GL),
                }
                options = {
                    **entry.options,
                    CONF_SCAN_INTERVAL_HOURS: scan,
                }
                self.hass.config_entries.async_update_entry(
                    entry, data=data, options=options
                )
                return self.async_abort(reason="settings_updated")
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PROVIDER, default=current_provider
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_provider_options())
                ),
                vol.Optional(CONF_API_KEY, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Optional(
                    CONF_BASE_URL, default=base_url_default
                ): selector.TextSelector(),
                vol.Optional(CONF_HL, default=hl_default): selector.TextSelector(),
                vol.Optional(CONF_GL, default=gl_default): selector.TextSelector(),
                vol.Required(
                    CONF_SCAN_INTERVAL_HOURS, default=scan_default
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_HOURS,
                        max=MAX_SCAN_INTERVAL_HOURS,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="h",
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="settings", data_schema=schema, errors=errors
        )

    async def _update_options(self, update: dict[str, Any]) -> None:
        options = {**self.entry.options, **update}
        self.hass.config_entries.async_update_entry(self.entry, options=options)


def _trip_defaults(trip: dict[str, Any]) -> dict[str, Any]:
    """Convert a stored trip dict into form defaults (date objects)."""
    return {
        CONF_TRIP_NAME: trip.get("name", ""),
        CONF_ORIGIN: trip.get("origin", ""),
        CONF_DESTINATION: trip.get("destination", ""),
        CONF_TRIP_TYPE: (
            TRIP_TYPE_ROUND_TRIP if trip.get("return_from") else TRIP_TYPE_ONE_WAY
        ),
        CONF_DATE_FROM: _parse_date(trip.get("date_from")),
        CONF_RETURN_FROM: _parse_date(trip.get("return_from")),
        CONF_PASSENGERS: trip.get("passengers", DEFAULT_PASSENGERS),
        CONF_MAX_STOPS: str(trip.get("max_stops", DEFAULT_MAX_STOPS)),
        CONF_CURRENCY: trip.get("currency", DEFAULT_CURRENCY),
        CONF_SEAT_CLASS: trip.get("seat_class", DEFAULT_SEAT_CLASS),
        CONF_TARGET_PRICE: trip.get("target_price"),
        CONF_NOTIFY_ON_TARGET: trip.get("notify_on_target", True),
    }


def _parse_date(value: Any) -> date_cls | None:
    if value is None:
        return None
    if isinstance(value, date_cls):
        return value
    try:
        return date_cls.fromisoformat(str(value))
    except ValueError:
        return None


async def _validate_key_for(
    hass: HomeAssistant, provider: str, api_key: str
) -> str | None:
    try:
        instance = get_provider(provider, hass, api_key)
    except ProviderError as err:
        return str(err)
    return await instance.validate_credentials()
