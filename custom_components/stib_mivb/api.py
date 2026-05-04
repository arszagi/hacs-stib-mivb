"""STIB/MIVB API client."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import aiohttp

from .const import (
    API_KEY_HEADER,
    API_STOP_DETAILS,
    API_STOPS_BY_LINE,
    API_WAITING_TIMES,
    LANGUAGE_FRENCH,
)

_LOGGER = logging.getLogger(__name__)


def _maybe_parse_json(value: Any) -> Any:
    """Parse a value that might be a JSON string."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _normalize_point_id(pid: str) -> str:
    """
    Strip trailing letter suffix from a point ID.

    The stop catalogue and stopsByLine use suffixed IDs (e.g. "5153F", "2934A")
    while the real-time WaitingTimes API returns bare numeric IDs ("5153", "2934").
    Normalising to the bare form allows cross-referencing between the two.
    """
    return pid.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


class StibMivbApiClient:
    """API client for STIB/MIVB open data."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        """Initialise the client."""
        self._session = session
        self._headers = {API_KEY_HEADER: api_key}
        # Full stop catalogue: { stop_id: {name_fr, name_nl, latitude, longitude} }
        self._stop_cache: dict[str, dict] = {}
        # Canonical destinations: { line_id: [{direction, dest_fr, dest_nl}] }
        self._line_dest_cache: dict[str, list[dict]] = {}

    async def _get(self, url: str, params: dict | None = None) -> dict:
        """Make a GET request and return the JSON response."""
        try:
            async with self._session.get(
                url,
                params=params,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            _LOGGER.error("Error fetching %s: %s", url, err)
            raise

    # ── Catalogue ────────────────────────────────────────────────────────────

    async def load_catalogue(self) -> None:
        """
        Download the full stop catalogue (~2445 stops) via pagination and
        store it in self._stop_cache.  Safe to call multiple times — a
        populated cache is never re-fetched.
        """
        if self._stop_cache:
            return

        _LOGGER.debug("Downloading full stop catalogue…")
        PAGE = 100
        offset = 0
        catalogue: dict[str, dict] = {}

        while True:
            try:
                data = await self._get(
                    API_STOP_DETAILS,
                    params={"limit": PAGE, "offset": offset},
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Catalogue fetch failed at offset %d: %s", offset, err
                )
                break

            results = data.get("results", [])
            total = data.get("total_count", 0)

            for row in results:
                sid = str(row.get("id", ""))
                if not sid:
                    continue
                name = _maybe_parse_json(row.get("name", {}))
                coords = _maybe_parse_json(row.get("gpscoordinates", {}))
                name_fr = name.get("fr", sid) if isinstance(name, dict) else str(name)
                name_nl = name.get("nl", name_fr) if isinstance(name, dict) else str(name)
                lat = coords.get("latitude") if isinstance(coords, dict) else None
                lon = coords.get("longitude") if isinstance(coords, dict) else None
                catalogue[sid] = {
                    "name_fr": name_fr,
                    "name_nl": name_nl,
                    "latitude": lat,
                    "longitude": lon,
                }

            offset += len(results)
            _LOGGER.debug("Catalogue: %d/%d stops loaded", offset, total)

            if not results or offset >= total:
                break

        _LOGGER.debug("Catalogue complete – %d stops loaded", len(catalogue))
        self._stop_cache = catalogue

    def search_stops(self, query: str, language: str = LANGUAGE_FRENCH) -> dict[str, dict]:
        """
        Search the cached catalogue for stops whose name contains `query`
        (case-insensitive).  Groups results by display name so that stops
        sharing a name (different physical platforms) are merged.

        Returns:
          {
            "FOREST NATIONAL": {
              "name_fr": "FOREST NATIONAL",
              "name_nl": "VORST NATIONAAL",
              "point_ids": ["2616B", "2732", "2953"],
              "latitude": 50.809...,   # from first matched point
              "longitude": 4.323...,
            },
            ...
          }
        """
        query_lower = query.strip().lower()
        grouped: dict[str, dict] = {}

        for sid, details in self._stop_cache.items():
            name_fr = details.get("name_fr", "")
            name_nl = details.get("name_nl", "")

            # Search in both languages
            if query_lower not in name_fr.lower() and query_lower not in name_nl.lower():
                continue

            # Group key is the display name in the chosen language
            group_key = name_fr if language == LANGUAGE_FRENCH else name_nl

            if group_key not in grouped:
                grouped[group_key] = {
                    "name_fr": name_fr,
                    "name_nl": name_nl,
                    "point_ids": [],
                    "latitude": details.get("latitude"),
                    "longitude": details.get("longitude"),
                }
            grouped[group_key]["point_ids"].append(sid)

        return dict(sorted(grouped.items()))

    # ── Waiting times ────────────────────────────────────────────────────────

    async def refresh_waiting_times_cache(self, point_ids: list[str] | None = None) -> None:
        """
        Download real-time WaitingTimes data and store it in self._rt_cache.

        When point_ids is provided the request is filtered server-side
        (``where=pointid in (id1, id2, ...)``) so only the stops we monitor
        are returned — typically a few KB instead of the ~1 MB full-network
        response.  This is the key optimisation to stay within API rate limits.

        Falls back to downloading the full dataset when point_ids is empty/None.
        """
        PAGE = 1000
        offset = 0
        cache: dict[str, list[dict]] = {}

        params_base: dict = {"limit": PAGE}
        if point_ids:
            bare_ids = sorted({_normalize_point_id(p) for p in point_ids if p})
            if bare_ids:
                params_base["where"] = f"pointid in ({', '.join(bare_ids)})"
                _LOGGER.debug(
                    "Fetching WaitingTimes for %d point IDs: %s", len(bare_ids), bare_ids
                )
            else:
                _LOGGER.debug("Fetching full WaitingTimes dataset (no point IDs provided)")
        else:
            _LOGGER.debug("Fetching full WaitingTimes dataset")

        while True:
            try:
                data = await self._get(
                    API_WAITING_TIMES,
                    params={**params_base, "offset": offset},
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("WaitingTimes fetch failed at offset %d: %s", offset, err)
                break

            results = data.get("results", [])
            total = data.get("total_count", 0)

            for row in results:
                pid = str(row.get("pointid", ""))
                bare = _normalize_point_id(pid)
                for key in {pid, bare}:
                    cache.setdefault(key, []).append(row)

            offset += len(results)
            _LOGGER.debug("WaitingTimes: %d/%d rows loaded", offset, total)

            if not results or offset >= total:
                break

        _LOGGER.debug("WaitingTimes cache ready — %d point IDs indexed", len(cache))
        self._rt_cache: dict[str, list[dict]] = cache

    def get_waiting_times_for_group(
        self, point_ids: list[str]
    ) -> list[dict]:
        """
        Filter the in-memory WaitingTimes cache for a stop group's point IDs.

        Must be called after refresh_waiting_times_cache().  No network I/O.

        Returns a list of:
          {
            "line_id": str,
            "direction": str,
            "rt_dest_fr": str,
            "rt_dest_nl": str,
            "minutes": int | None,
            "current_passage": str | None,
            "next_passage": str | None,
            "point_id": str,
          }
        """
        rt_cache = getattr(self, "_rt_cache", {})
        pid_index = getattr(self, "_point_to_lines", {})

        # Collect all rows from the cache that match any of our point IDs
        all_point_id_forms: set[str] = set(point_ids) | {_normalize_point_id(p) for p in point_ids}
        rows: list[tuple[str, dict]] = []  # (original_pid, row)
        seen_rows: set[int] = set()
        for pid in all_point_id_forms:
            for row in rt_cache.get(pid, []):
                rid = id(row)
                if rid not in seen_rows:
                    seen_rows.add(rid)
                    rows.append((pid, row))

        # Merge into one entry per (line_id, direction)
        merged: dict[tuple, dict] = {}

        for row_pid, row in rows:
            line_id = str(row.get("lineid", ""))
            passing_times = _maybe_parse_json(row.get("passingtimes", []))
            if not isinstance(passing_times, list) or not passing_times:
                continue

            first = passing_times[0]
            destination = first.get("destination", {})
            dest_fr = destination.get("fr", "") if isinstance(destination, dict) else str(destination)
            dest_nl = destination.get("nl", dest_fr) if isinstance(destination, dict) else str(destination)
            expected = first.get("expectedArrivalTime")
            minutes = self._minutes_until(expected)
            next_passage = passing_times[1].get("expectedArrivalTime") if len(passing_times) > 1 else None

            message_obj = first.get("message", {})
            message_fr = message_obj.get("fr", "") if isinstance(message_obj, dict) else ""
            is_boarding = message_fr != "Ne pas embarquer"

            # Resolve direction from the static index
            direction = ""
            for lookup_pid in (row_pid, _normalize_point_id(row_pid)):
                for entry in pid_index.get(lookup_pid, []):
                    if entry["line_id"] == line_id:
                        direction = entry["direction"]
                        break
                if direction:
                    break

            key = (line_id, direction)
            existing = merged.get(key)
            if existing is None or (
                minutes is not None
                and (existing["minutes"] is None or minutes < existing["minutes"])
            ):
                merged[key] = {
                    "line_id": line_id,
                    "direction": direction,
                    "rt_dest_fr": dest_fr,
                    "rt_dest_nl": dest_nl,
                    "minutes": minutes,
                    "current_passage": expected,
                    "next_passage": next_passage,
                    "point_id": row_pid,
                    "message": message_fr,
                    "is_boarding": is_boarding,
                }

        return list(merged.values())

    # ── Lines serving a set of point IDs ────────────────────────────────────

    async def get_lines_for_points(self, point_ids: list[str]) -> dict[str, list[dict]]:
        """
        Discover all lines serving the given point IDs using two targeted calls
        instead of downloading the full stopsByLine dataset.

        Step 1 — WaitingTimes (filtered by point_ids) → extract which lineids
                  are currently active at our stops.
        Step 2 — stopsByLine (filtered by lineids) → fetch canonical destinations
                  and direction for only those lines.

        Side-effect: populates self._point_to_lines for direction resolution in
        get_waiting_times_for_group().

        Returns:
          {
            "54": [
              {"dest_fr": "FOREST (BERVOETS)", "dest_nl": "VORST (BERVOETS)", "direction": "Suburb"},
              {"dest_fr": "TRONE",             "dest_nl": "TROON",            "direction": "City"},
            ],
            ...
          }
          If no vehicles are active (e.g. at night), returns {} and logs a warning;
          sensors will be created from the first real-time coordinator update instead.
        """
        bare_ids = sorted({_normalize_point_id(p) for p in point_ids if p})
        all_ids: set[str] = set(point_ids) | set(bare_ids)

        # ── Step 1: discover which lineids serve our stops ────────────────────
        lineids: set[str] = set()
        try:
            data = await self._get(
                API_WAITING_TIMES,
                params={"limit": 1000, "where": f"pointid in ({', '.join(bare_ids)})"},
            )
            for row in data.get("results", []):
                lid = str(row.get("lineid", ""))
                if lid:
                    lineids.add(lid)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Could not discover line IDs for stops %s: %s", bare_ids, err)

        if not lineids:
            _LOGGER.warning(
                "No active vehicles found for stops %s — static skeleton will be empty. "
                "Sensors will appear after the first successful real-time update.",
                bare_ids,
            )
            self._point_to_lines: dict[str, list[dict]] = {}
            return {}

        # ── Step 2: fetch stopsByLine filtered to discovered lines ────────────
        line_filter = f"lineid in ({', '.join(sorted(lineids))})"
        _LOGGER.debug("Fetching stopsByLine for lines %s", sorted(lineids))

        index: dict[str, list[dict]] = {}
        result: dict[str, list[dict]] = {}
        PAGE = 100
        offset = 0

        while True:
            try:
                data = await self._get(
                    API_STOPS_BY_LINE,
                    params={"limit": PAGE, "offset": offset, "where": line_filter},
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("stopsByLine fetch failed at offset %d: %s", offset, err)
                break

            results = data.get("results", [])
            total = data.get("total_count", 0)

            for row in results:
                line_id = str(row.get("lineid", ""))
                direction = row.get("direction", "")
                destination = _maybe_parse_json(row.get("destination", {}))
                dest_fr = destination.get("fr", "") if isinstance(destination, dict) else str(destination)
                dest_nl = destination.get("nl", dest_fr) if isinstance(destination, dict) else str(destination)
                points = _maybe_parse_json(row.get("points", []))
                if not isinstance(points, list):
                    continue

                valid_pts = [p for p in points if isinstance(p, dict)]
                entry = {
                    "line_id": line_id,
                    "dest_fr": dest_fr,
                    "dest_nl": dest_nl,
                    "direction": direction,
                }

                for pt in valid_pts:
                    pid = str(pt.get("id", ""))
                    if not pid:
                        continue
                    bare_pid = _normalize_point_id(pid)

                    # Full point→lines index for direction resolution (all stops on these lines)
                    for key in {pid, bare_pid}:
                        if key not in index:
                            index[key] = []
                        if entry not in index[key]:
                            index[key].append(entry)

                    # Result dict: only for our configured stops
                    if pid in all_ids or bare_pid in all_ids:
                        if line_id not in result:
                            result[line_id] = []
                        direction_entry = {
                            "dest_fr": dest_fr,
                            "dest_nl": dest_nl,
                            "direction": direction,
                        }
                        if direction_entry not in result[line_id]:
                            result[line_id].append(direction_entry)

            offset += len(results)
            _LOGGER.debug("stopsByLine: %d/%d rows processed", offset, total)

            if not results or offset >= total:
                break

        _LOGGER.debug(
            "Lines for stops %s: %s",
            bare_ids,
            {lid: [d["direction"] for d in dirs] for lid, dirs in result.items()},
        )
        self._point_to_lines = index
        return result

    # ── Canonical line destinations ──────────────────────────────────────────

    async def get_line_destinations(self, line_id: str) -> list[dict]:
        """
        Return the canonical destinations for a line from stopsByLine.

        Uses a per-instance cache so repeated calls for the same line are free.

        Returns a list of:
          { "direction": str, "dest_fr": str, "dest_nl": str }
        """
        if line_id in self._line_dest_cache:
            return self._line_dest_cache[line_id]

        try:
            data = await self._get(
                API_STOPS_BY_LINE, params={"where": f"lineid={line_id}"}
            )
            results = data.get("results", [])
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Could not fetch destinations for line %s: %s", line_id, err)
            return []

        destinations: list[dict] = []
        for row in results:
            direction = row.get("direction", "")
            destination = _maybe_parse_json(row.get("destination", {}))
            dest_fr = destination.get("fr", "") if isinstance(destination, dict) else str(destination)
            dest_nl = destination.get("nl", dest_fr) if isinstance(destination, dict) else str(destination)
            destinations.append({
                "direction": direction,
                "dest_fr": dest_fr,
                "dest_nl": dest_nl,
            })

        self._line_dest_cache[line_id] = destinations
        _LOGGER.debug(
            "Canonical destinations for line %s: %s",
            line_id,
            [(d["direction"], d["dest_fr"]) for d in destinations],
        )
        return destinations

    # ── Single stop detail (used for API key validation) ─────────────────────

    async def get_stop_details(self, stop_id: str) -> dict:
        """Return details for a single stop — used to validate the API key."""
        try:
            data = await self._get(API_STOP_DETAILS, params={"where": f"id={stop_id}"})
            results = data.get("results", [])
            if not results:
                return {}
            row = results[0]
            name = _maybe_parse_json(row.get("name", {}))
            coords = _maybe_parse_json(row.get("gpscoordinates", {}))
            name_fr = name.get("fr", stop_id) if isinstance(name, dict) else str(name)
            name_nl = name.get("nl", name_fr) if isinstance(name, dict) else str(name)
            return {
                "name_fr": name_fr,
                "name_nl": name_nl,
                "latitude": coords.get("latitude") if isinstance(coords, dict) else None,
                "longitude": coords.get("longitude") if isinstance(coords, dict) else None,
            }
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Could not fetch details for stop %s: %s", stop_id, err)
            return {}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _minutes_until(iso_timestamp: str | None) -> int | None:
        """Return whole minutes from now until the given ISO timestamp."""
        if not iso_timestamp:
            return None
        try:
            from datetime import timezone
            arrival = datetime.fromisoformat(iso_timestamp)
            # If the API returns a naive timestamp, treat it as UTC to avoid
            # a TypeError when mixing aware/naive datetimes in subtraction.
            if arrival.tzinfo is None:
                arrival = arrival.replace(tzinfo=timezone.utc)
            now = datetime.now(tz=arrival.tzinfo)
            delta = (arrival - now).total_seconds()
            return max(0, int(delta // 60))
        except (ValueError, TypeError):
            return None
