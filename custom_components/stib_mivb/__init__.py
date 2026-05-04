"""STIB/MIVB integration for Home Assistant."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import StibMivbApiClient, _normalize_point_id
from .const import (
    CONF_API_KEY,
    CONF_LINE_INFO,
    CONF_SCAN_INTERVAL,
    CONF_STOP_GROUPS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    STIB_LINE_INFO,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up STIB/MIVB from a config entry."""
    session = async_get_clientsession(hass)
    api_key = entry.data.get(CONF_API_KEY, "")
    client = StibMivbApiClient(session, api_key)

    # Verify connectivity / API key validity.
    # get_stop_details() catches all exceptions internally and returns {} on failure,
    # so we check for an empty result regardless of whether it was a network or auth error.
    try:
        details = await client.get_stop_details("2935")
        if not details:
            raise ConfigEntryNotReady("Cannot connect to STIB/MIVB API or invalid API key")
    except ConfigEntryNotReady:
        raise
    except Exception as err:
        raise ConfigEntryNotReady(f"Cannot connect to STIB/MIVB API: {err}") from err

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    # Load GTFS line info — use cache from options when available, otherwise download.
    # This download happens at every fresh install; on subsequent starts the cached
    # data from entry.options is used.  The user can force a refresh via Options flow.
    cached_line_info: dict = entry.options.get(CONF_LINE_INFO, {})
    if not cached_line_info:
        _LOGGER.debug("No cached GTFS line info — downloading routes.txt...")
        cached_line_info = await client.load_line_info()
        if cached_line_info:
            # Persist to options BEFORE the update-listener is registered so this
            # write does not trigger a reload of the entry.
            hass.config_entries.async_update_entry(
                entry, options={**entry.options, CONF_LINE_INFO: cached_line_info}
            )
        else:
            _LOGGER.warning("GTFS download failed — using built-in line data as fallback")

    # Merge: built-in hardcoded dict as base, GTFS as override (more up-to-date)
    line_info: dict = {**STIB_LINE_INFO, **cached_line_info}

    coordinator = StibMivbCoordinator(hass, client, entry, scan_interval, line_info)

    # Build the static line skeleton before the first refresh so that sensors
    # for ALL lines serving a stop are created immediately — even when no
    # vehicle is currently en route (which would make them invisible in rt data).
    await coordinator.async_build_static_lines()

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


class StibMivbCoordinator(DataUpdateCoordinator):
    """Coordinator that fetches waiting times for all configured stop groups."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: StibMivbApiClient,
        entry: ConfigEntry,
        scan_interval: int,
        line_info: dict,
    ) -> None:
        """Initialise coordinator."""
        self.client = client
        self.entry = entry
        self.line_info: dict = line_info
        # Static skeleton: { name_fr: [ {line_id, dest_fr, dest_nl, direction} ] }
        # Built once at setup via async_build_static_lines().
        # This is what sensor.py uses to pre-create all sensors.
        self.static_lines: dict[str, list[dict]] = {}
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def async_build_static_lines(self) -> None:
        """
        Discover every line serving any configured stop group and populate
        self.static_lines so sensors exist for all lines upfront.

        A single combined API call is made for ALL groups together, so startup
        costs exactly 2 requests regardless of how many stop groups are configured.
        The resulting _point_to_lines index covers all groups, which is also needed
        for correct direction resolution during every subsequent refresh.
        """
        groups = self.entry.options.get(CONF_STOP_GROUPS) or self.entry.data.get(CONF_STOP_GROUPS, [])
        if not groups:
            return

        # One combined call for all groups — populates client._point_to_lines
        all_point_ids: list[str] = [
            pid for group in groups for pid in group.get("point_ids", [])
        ]
        try:
            await self.client.get_lines_for_points(all_point_ids)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Could not build static lines: %s", err)
            for group in groups:
                self.static_lines[group["name_fr"]] = []
            return

        # Reconstruct per-group skeletons from the now-populated _point_to_lines index
        pid_index: dict = getattr(self.client, "_point_to_lines", {})

        for group in groups:
            name_fr = group["name_fr"]
            point_ids = group.get("point_ids", [])
            seen: set[tuple[str, str]] = set()
            skeletons: list[dict] = []

            for pid in point_ids:
                for lookup in {pid, _normalize_point_id(pid)}:
                    for entry in pid_index.get(lookup, []):
                        key = (entry["line_id"], entry["direction"])
                        if key not in seen:
                            seen.add(key)
                            skeletons.append({
                                "line_id": entry["line_id"],
                                "dest_fr": entry["dest_fr"],
                                "dest_nl": entry["dest_nl"],
                                "direction": entry["direction"],
                                "minutes": None,
                                "next_passage": None,
                                "rt_dest_fr": None,
                                "rt_dest_nl": None,
                                "point_id": None,
                            })

            self.static_lines[name_fr] = skeletons
            _LOGGER.debug(
                "Static lines for %s: %s",
                name_fr,
                [(s["line_id"], s["dest_fr"]) for s in skeletons],
            )

    async def _async_update_data(self) -> dict:
        """
        Fetch real-time waiting times for every stop group and merge them on top
        of the static skeleton so that:
          - Every statically known line always has a sensor (minutes=None when
            no vehicle is currently en route).
          - Short-turn destinations from rt data are matched to the canonical
            (static) destination and do not create duplicate sensors.

        Coordinator data structure per stop group:
          [
            {
              "line_id":      str,
              "dest_fr":      str,   # canonical end-of-line destination (FR)
              "dest_nl":      str,   # canonical end-of-line destination (NL)
              "direction":    str,   # "City" | "Suburb"
              "rt_dest_fr":   str | None,  # real-time destination (may be short-turn)
              "rt_dest_nl":   str | None,
              "minutes":      int | None,
              "next_passage": str | None,
              "point_id":     str | None,
            },
            ...
          ]
        """
        groups = self.entry.options.get(CONF_STOP_GROUPS) or self.entry.data.get(CONF_STOP_GROUPS, [])
        data: dict = {}

        # Collect all monitored point IDs so the API call is filtered server-side.
        # This reduces the response from ~1 MB (full network) to a few KB.
        all_point_ids: list[str] = [
            pid
            for group in groups
            for pid in group.get("point_ids", [])
        ]

        try:
            await self.client.refresh_waiting_times_cache(point_ids=all_point_ids)
        except Exception as err:  # noqa: BLE001
            if not hasattr(self.client, "_rt_cache"):
                raise UpdateFailed(f"WaitingTimes bulk refresh failed: {err}") from err
            _LOGGER.warning("WaitingTimes bulk refresh failed, using previous cache: %s", err)

        for group in groups:
            name_fr = group["name_fr"]
            point_ids = group.get("point_ids", [])

            # Start from the static skeleton (all lines, minutes=None)
            skeleton: dict[tuple, dict] = {}
            for s in self.static_lines.get(name_fr, []):
                key = (s["line_id"], s["dest_fr"])
                skeleton[key] = dict(s)  # copy so we don't mutate static_lines

            try:
                rt_passages = self.client.get_waiting_times_for_group(point_ids)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Real-time filter failed for %s: %s", name_fr, err)
                data[name_fr] = list(skeleton.values())
                continue

            # Merge real-time data into the skeleton.
            # The rt passage carries a direction resolved from the stopsByLine
            # index in api.py, so we can match precisely on (line_id, direction).
            # This correctly handles lines with two directions (e.g. City/Suburb)
            # and short-turns: a NEERSTALLE rt result for line 50 Suburb matches
            # the GARE DU MIDI skeleton entry because both share direction=Suburb.
            for p in rt_passages:
                line_id = p["line_id"]
                direction = p.get("direction", "")
                rt_dest_fr = p.get("rt_dest_fr", "")

                # 1) Exact match on (line_id, direction)
                matched_key = next(
                    (k for k in skeleton if k[0] == line_id and skeleton[k].get("direction") == direction),
                    None,
                )
                # 2) Fallback: any entry for this line (e.g. direction unknown)
                if matched_key is None:
                    matched_key = next(
                        (k for k in skeleton if k[0] == line_id),
                        None,
                    )

                if matched_key is not None:
                    skeleton[matched_key].update({
                        "rt_dest_fr": rt_dest_fr,
                        "rt_dest_nl": p.get("rt_dest_nl"),
                        "minutes": p.get("minutes"),
                        "next_passage": p.get("next_passage"),
                        "point_id": p.get("point_id"),
                        "message": p.get("message", ""),
                        "is_boarding": p.get("is_boarding", True),
                    })
                else:
                    # Line not in static skeleton (shouldn't normally happen);
                    # add it anyway with rt destination as canonical fallback.
                    _LOGGER.debug(
                        "Line %s direction=%s at %s not in static skeleton, adding from rt",
                        line_id, direction, name_fr,
                    )
                    skeleton[(line_id, rt_dest_fr)] = {
                        "line_id": line_id,
                        "dest_fr": rt_dest_fr,
                        "dest_nl": p.get("rt_dest_nl", ""),
                        "direction": direction,
                        "rt_dest_fr": rt_dest_fr,
                        "rt_dest_nl": p.get("rt_dest_nl"),
                        "minutes": p.get("minutes"),
                        "next_passage": p.get("next_passage"),
                        "point_id": p.get("point_id"),
                        "message": p.get("message", ""),
                        "is_boarding": p.get("is_boarding", True),
                    }

            data[name_fr] = list(skeleton.values())

        return data
