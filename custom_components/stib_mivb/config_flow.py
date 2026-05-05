"""Config flow for STIB/MIVB integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import StibMivbApiClient
from .const import (
    CONF_API_KEY,
    CONF_LANGUAGE,
    CONF_LINE_INFO,
    CONF_SCAN_INTERVAL,
    CONF_STOP_GROUPS,
    CONF_STOP_NAME,
    CONF_STOP_SEARCH,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LANGUAGE_DUTCH,
    LANGUAGE_FRENCH,
)

_LOGGER = logging.getLogger(__name__)


class StibMivbConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the STIB/MIVB config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise."""
        self._language: str = LANGUAGE_FRENCH
        self._api_key: str = ""
        self._client: StibMivbApiClient | None = None
        self._configured_groups: list[dict] = []
        # Search state
        self._search_results: dict[str, dict] = {}  # display_name → group dict

    # ── Step 1: language + API key ────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Choose language and enter API key."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        errors: dict[str, str] = {}

        if user_input is not None:
            self._language = user_input[CONF_LANGUAGE]
            self._api_key = user_input[CONF_API_KEY].strip()

            session = async_get_clientsession(self.hass)
            self._client = StibMivbApiClient(session, self._api_key)

            # Validate key with a quick test call
            try:
                details = await self._client.get_stop_details("2935")
                if not details:
                    errors[CONF_API_KEY] = "invalid_api_key"
                else:
                    # Key is valid — download the full catalogue
                    await self._client.load_catalogue()
                    return await self.async_step_search()
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_LANGUAGE, default=LANGUAGE_FRENCH): vol.In(
                    {LANGUAGE_FRENCH: "Français", LANGUAGE_DUTCH: "Nederlands"}
                ),
                vol.Required(CONF_API_KEY): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # ── Step 2: search by name ────────────────────────────────────────────────

    async def async_step_search(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Enter a search term to find stop names."""
        errors: dict[str, str] = {}

        if user_input is not None:
            query = user_input.get(CONF_STOP_SEARCH, "").strip()
            if len(query) < 2:
                errors[CONF_STOP_SEARCH] = "search_too_short"
            else:
                self._search_results = self._client.search_stops(query, self._language)
                if not self._search_results:
                    errors[CONF_STOP_SEARCH] = "no_results"
                else:
                    return await self.async_step_pick_stop()

        schema = vol.Schema({vol.Required(CONF_STOP_SEARCH): str})
        return self.async_show_form(
            step_id="search",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "already_added": ", ".join(
                    g["name_fr"] for g in self._configured_groups
                ) or "none"
            },
        )

    # ── Step 3: pick one stop name from search results ────────────────────────

    async def async_step_pick_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Select a stop name from the search results."""
        errors: dict[str, str] = {}

        if user_input is not None:
            chosen_name = user_input[CONF_STOP_NAME]
            group = self._search_results.get(chosen_name)
            if group:
                # Avoid exact duplicates (same name_fr already added)
                already = {g["name_fr"] for g in self._configured_groups}
                if group["name_fr"] not in already:
                    self._configured_groups.append(group)
            self._search_results = {}
            return await self.async_step_confirm()

        # Build option list: display_name → "NAME (N platforms)"
        options = {
            name: f"{name}  ({len(g['point_ids'])} platform{'s' if len(g['point_ids']) > 1 else ''})"
            for name, g in self._search_results.items()
        }

        schema = vol.Schema(
            {vol.Required(CONF_STOP_NAME): vol.In(options)}
        )
        return self.async_show_form(
            step_id="pick_stop", data_schema=schema, errors=errors
        )

    # ── Step 4: confirm + add more or finish ─────────────────────────────────

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show configured stops and offer to add more or finish."""
        if user_input is not None:
            action = user_input.get("action", "finish")
            if action == "add_more":
                return await self.async_step_search()
            return self._create_entry()

        stops_summary = "\n".join(
            f"• {g['name_fr']} / {g['name_nl']}  [{', '.join(g['point_ids'])}]"
            for g in self._configured_groups
        )

        schema = vol.Schema(
            {
                vol.Required("action", default="finish"): vol.In(
                    {"finish": "Finish setup", "add_more": "Add another stop"}
                )
            }
        )
        return self.async_show_form(
            step_id="confirm",
            data_schema=schema,
            description_placeholders={"stops_summary": stops_summary or "None"},
        )

    def _create_entry(self) -> config_entries.FlowResult:
        return self.async_create_entry(
            title="STIB/MIVB",
            data={
                CONF_API_KEY: self._api_key,
                CONF_LANGUAGE: self._language,
                CONF_STOP_GROUPS: self._configured_groups,
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Allow changing the API key without removing the integration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            session = async_get_clientsession(self.hass)
            client = StibMivbApiClient(session, api_key)

            try:
                details = await client.get_stop_details("2935")
                if not details:
                    errors[CONF_API_KEY] = "invalid_api_key"
                else:
                    return self.async_update_reload_and_abort(
                        self._get_reconfigure_entry(),
                        data_updates={CONF_API_KEY: api_key},
                    )
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"

        schema = vol.Schema({vol.Required(CONF_API_KEY): str})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> StibMivbOptionsFlow:
        """Return the options flow."""
        return StibMivbOptionsFlow()


class StibMivbOptionsFlow(config_entries.OptionsFlow):
    """Options: add/remove stop groups, scan interval."""

    def __init__(self) -> None:
        """Initialise — config_entry is available via self.config_entry once the flow starts."""
        self._configured_groups: list[dict] | None = None
        self._line_info: dict = {}
        self._client: StibMivbApiClient | None = None
        self._search_results: dict[str, dict] = {}
        self._language: str = LANGUAGE_FRENCH

    async def _ensure_client(self) -> None:
        """Create and warm up the API client if not done yet."""
        if self._client is None:
            session = async_get_clientsession(self.hass)
            api_key = self.config_entry.data.get(CONF_API_KEY, "")
            self._client = StibMivbApiClient(session, api_key)
            await self._client.load_catalogue()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Options menu."""
        # Initialize state from config_entry on first call (not available in __init__).
        if self._configured_groups is None:
            self._configured_groups = list(
                self.config_entry.options.get(CONF_STOP_GROUPS)
                or self.config_entry.data.get(CONF_STOP_GROUPS, [])
            )
            self._language = self.config_entry.data.get(CONF_LANGUAGE, LANGUAGE_FRENCH)
            self._line_info = dict(self.config_entry.options.get(CONF_LINE_INFO, {}))

        if user_input is not None:
            action = user_input.get("action", "finish")
            if action == "add_stop":
                await self._ensure_client()
                return await self.async_step_search()
            if action == "remove_stop":
                return await self.async_step_remove_stop()
            if action == "refresh_lines":
                return await self.async_step_refresh_lines()
            return self.async_create_entry(
                title="",
                data={
                    CONF_STOP_GROUPS: self._configured_groups,
                    CONF_SCAN_INTERVAL: user_input.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                    CONF_LINE_INFO: self._line_info,
                },
            )

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        actions: dict[str, str] = {
            "finish": "Save & close",
            "add_stop": "Add another stop",
        }
        if self._configured_groups:
            actions["remove_stop"] = "Remove a stop"
        actions["refresh_lines"] = "Refresh line colours & types (GTFS)"

        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                    int, vol.Range(min=10, max=3600)
                ),
                vol.Required("action", default="finish"): vol.In(actions),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_remove_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Select a configured stop to remove."""
        if user_input is not None:
            name_to_remove = user_input.get("stop_to_remove")
            self._configured_groups = [
                g for g in self._configured_groups if g["name_fr"] != name_to_remove
            ]
            return await self.async_step_init()

        options = {
            g["name_fr"]: f"{g['name_fr']} / {g['name_nl']}  [{len(g.get('point_ids', []))} platform{'s' if len(g.get('point_ids', [])) > 1 else ''}]"
            for g in self._configured_groups
        }
        schema = vol.Schema({vol.Required("stop_to_remove"): vol.In(options)})
        return self.async_show_form(step_id="remove_stop", data_schema=schema)

    async def async_step_refresh_lines(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Download fresh GTFS data and report how many lines were loaded."""
        errors: dict[str, str] = {}
        line_count = 0

        if user_input is None:
            # First call: do the download, then show the result form
            try:
                session = async_get_clientsession(self.hass)
                api_key = self.config_entry.data.get(CONF_API_KEY, "")
                client = StibMivbApiClient(session, api_key)
                new_info = await client.load_line_info()
                if new_info:
                    self._line_info = new_info
                    line_count = len(new_info)
                else:
                    errors["base"] = "gtfs_failed"
            except Exception:  # noqa: BLE001
                errors["base"] = "gtfs_failed"

            return self.async_show_form(
                step_id="refresh_lines",
                data_schema=vol.Schema({}),
                description_placeholders={"line_count": str(line_count)},
                errors=errors,
            )

        # Second call (user clicked OK): go back to the options menu
        return await self.async_step_init()

    async def async_step_search(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Search for a stop by name."""
        errors: dict[str, str] = {}

        if self._client is None:
            await self._ensure_client()

        if user_input is not None:
            query = user_input.get(CONF_STOP_SEARCH, "").strip()
            if len(query) < 2:
                errors[CONF_STOP_SEARCH] = "search_too_short"
            else:
                self._search_results = self._client.search_stops(query, self._language)
                if not self._search_results:
                    errors[CONF_STOP_SEARCH] = "no_results"
                else:
                    return await self.async_step_pick_stop()

        schema = vol.Schema({vol.Required(CONF_STOP_SEARCH): str})
        return self.async_show_form(step_id="search", data_schema=schema, errors=errors)

    async def async_step_pick_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Pick a stop from search results."""
        if user_input is not None:
            chosen_name = user_input[CONF_STOP_NAME]
            group = self._search_results.get(chosen_name)
            if group:
                already = {g["name_fr"] for g in self._configured_groups}
                if group["name_fr"] not in already:
                    self._configured_groups.append(group)
            self._search_results = {}
            return await self.async_step_init()

        options = {
            name: f"{name}  ({len(g['point_ids'])} platform{'s' if len(g['point_ids']) > 1 else ''})"
            for name, g in self._search_results.items()
        }
        schema = vol.Schema({vol.Required(CONF_STOP_NAME): vol.In(options)})
        return self.async_show_form(step_id="pick_stop", data_schema=schema)
