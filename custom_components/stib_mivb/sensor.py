"""Sensor platform for STIB/MIVB."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StibMivbCoordinator
from .const import (
    ATTR_DESTINATION,
    ATTR_DIRECTION,
    ATTR_IS_BOARDING,
    ATTR_LATITUDE,
    ATTR_LINE_ID,
    ATTR_LONGITUDE,
    ATTR_MESSAGE,
    ATTR_NEXT_PASSAGE,
    ATTR_POINT_IDS,
    ATTR_STOP_NAME_FR,
    ATTR_STOP_NAME_NL,
    ATTR_VEHICLE_DISTANCE,
    CONF_LANGUAGE,
    CONF_STOP_GROUPS,
    DOMAIN,
    LANGUAGE_FRENCH,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up STIB/MIVB sensors from a config entry."""
    coordinator: StibMivbCoordinator = hass.data[DOMAIN][entry.entry_id]
    language = entry.data.get(CONF_LANGUAGE, LANGUAGE_FRENCH)
    groups = entry.options.get(CONF_STOP_GROUPS) or entry.data.get(CONF_STOP_GROUPS, [])

    entities: list[SensorEntity] = []

    for group in groups:
        skeletons = coordinator.static_lines.get(group["name_fr"], [])
        if not skeletons:
            skeletons = (coordinator.data or {}).get(group["name_fr"], [])

        # Wait time sensors — one per (line, direction)
        for skeleton in skeletons:
            entities.append(StibMivbSensor(coordinator, group, skeleton, language))

        # Vehicle distance sensors — one per (line, direction)
        for skeleton in skeletons:
            entities.append(StibMivbVehicleSensor(coordinator, group, skeleton, language))

    async_add_entities(entities, update_before_add=False)


def _slug(text: str) -> str:
    return (
        text.lower()
        .replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("-", "_")
        .replace("/", "_")
        .replace("'", "")
    )


class StibMivbSensor(CoordinatorEntity[StibMivbCoordinator], SensorEntity):
    """
    Sensor representing the waiting time for one line at a named stop group.

    Device  = stop name  (e.g. "FOREST NATIONAL")
    Sensor  = line + destination  (e.g. "Line 54 → FOREST (BERVOETS)")
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "min"
    _attr_icon = "mdi:bus-clock"

    def __init__(
        self,
        coordinator: StibMivbCoordinator,
        group: dict,
        passage: dict,
        language: str,
    ) -> None:
        super().__init__(coordinator)
        self._language = language
        self._name_fr: str = group["name_fr"]
        self._name_nl: str = group["name_nl"]
        self._point_ids: list[str] = group.get("point_ids", [])
        self._latitude = group.get("latitude")
        self._longitude = group.get("longitude")

        self._line_id: str = passage["line_id"]
        self._dest_fr: str = passage.get("dest_fr") or passage.get("rt_dest_fr", "")
        self._dest_nl: str = passage.get("dest_nl") or passage.get("rt_dest_nl", "")

        stop_display = self._name_fr if language == LANGUAGE_FRENCH else self._name_nl
        dest_display = self._dest_fr if language == LANGUAGE_FRENCH else self._dest_nl

        stop_slug = _slug(self._name_fr)
        dest_slug = _slug(self._dest_fr)
        first_pid = self._point_ids[0] if self._point_ids else "unknown"

        self._attr_unique_id = f"{DOMAIN}_{first_pid}_{self._line_id}_{stop_slug}_{dest_slug}"
        self._attr_name = f"Line {self._line_id} – {stop_display} → {dest_display}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"stop_group_{self._name_fr}")},
            name=stop_display,
            manufacturer="STIB/MIVB",
            model=f"Stop group – {', '.join(self._point_ids)}",
        )

    @property
    def _current_passage(self) -> dict:
        passages = (self.coordinator.data or {}).get(self._name_fr, [])
        for p in passages:
            if p["line_id"] == self._line_id and (
                p.get("dest_fr") == self._dest_fr
                or p.get("rt_dest_fr") == self._dest_fr
            ):
                return p
        return {}

    @property
    def native_value(self) -> int | None:
        return self._current_passage.get("minutes")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        p = self._current_passage
        dest = self._dest_fr if self._language == LANGUAGE_FRENCH else self._dest_nl
        next_passage_ts = p.get("next_passage")
        next_passage_minutes = self.coordinator.client._minutes_until(next_passage_ts)

        return {
            "current_passage": p.get("current_passage"),
            ATTR_NEXT_PASSAGE: next_passage_ts,
            "next_passage_minutes": next_passage_minutes,
            ATTR_LATITUDE: self._latitude,
            ATTR_LONGITUDE: self._longitude,
            ATTR_STOP_NAME_FR: self._name_fr,
            ATTR_STOP_NAME_NL: self._name_nl,
            ATTR_DESTINATION: dest,
            ATTR_LINE_ID: self._line_id,
            ATTR_POINT_IDS: self._point_ids,
            ATTR_MESSAGE: p.get("message", ""),
            ATTR_IS_BOARDING: p.get("is_boarding", True),
            ATTR_VEHICLE_DISTANCE: p.get("vehicle_distance_m"),
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success


class StibMivbVehicleSensor(CoordinatorEntity[StibMivbCoordinator], SensorEntity):
    """
    Sensor showing the distance in metres of the nearest vehicle of a line
    heading in the correct direction towards this stop.

    One sensor per (line, direction) — same granularity as wait-time sensors.

    Device  = stop name  (e.g. "FOREST NATIONAL")
    Sensor  = "Line 54 – FOREST NATIONAL → BOONDAEL GARE [vehicle]"
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "m"
    _attr_icon = "mdi:map-marker-distance"

    def __init__(
        self,
        coordinator: StibMivbCoordinator,
        group: dict,
        passage: dict,
        language: str,
    ) -> None:
        super().__init__(coordinator)
        self._language = language
        self._name_fr: str = group["name_fr"]
        self._name_nl: str = group["name_nl"]
        self._point_ids: list[str] = group.get("point_ids", [])
        self._line_id: str = passage["line_id"]
        self._direction: str = passage.get("direction", "")
        self._dest_fr: str = passage.get("dest_fr") or passage.get("rt_dest_fr", "")
        self._dest_nl: str = passage.get("dest_nl") or passage.get("rt_dest_nl", "")

        stop_display = self._name_fr if language == LANGUAGE_FRENCH else self._name_nl
        dest_display = self._dest_fr if language == LANGUAGE_FRENCH else self._dest_nl

        stop_slug = _slug(self._name_fr)
        dest_slug = _slug(self._dest_fr)
        first_pid = self._point_ids[0] if self._point_ids else "unknown"

        self._attr_unique_id = f"{DOMAIN}_{first_pid}_{self._line_id}_{stop_slug}_{dest_slug}_vehicle"
        self._attr_name = f"Line {self._line_id} – {stop_display} → {dest_display} [vehicle]"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"stop_group_{self._name_fr}")},
            name=stop_display,
            manufacturer="STIB/MIVB",
            model=f"Stop group – {', '.join(self._point_ids)}",
        )

    @property
    def _current_passage(self) -> dict:
        passages = (self.coordinator.data or {}).get(self._name_fr, [])
        for p in passages:
            if p["line_id"] == self._line_id and (
                p.get("dest_fr") == self._dest_fr
                or p.get("rt_dest_fr") == self._dest_fr
            ):
                return p
        return {}

    @property
    def native_value(self) -> int | None:
        p = self._current_passage
        dist = p.get("vehicle_distance_m")
        # Hide distance when the vehicle is not boarding (already departed)
        if dist is not None and not p.get("is_boarding", True) and dist == 0:
            return None
        return dist

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        p = self._current_passage
        return {
            ATTR_LINE_ID: self._line_id,
            ATTR_DIRECTION: self._direction,
            ATTR_STOP_NAME_FR: self._name_fr,
            ATTR_STOP_NAME_NL: self._name_nl,
            ATTR_POINT_IDS: self._point_ids,
            ATTR_IS_BOARDING: p.get("is_boarding", True),
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success
