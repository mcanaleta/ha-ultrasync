"""Coordinate polling and commands for an UltraSync panel."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta
from functools import partial
from typing import Any, TypeVar

from homeassistant.const import CONF_HOST, CONF_PIN, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

import ultrasync

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_ResultT = TypeVar("_ResultT")


class UltraSyncCommandError(RuntimeError):
    """Raised when a panel rejects or fails to execute a command."""


class UltraSyncUnsupportedError(UltraSyncCommandError):
    """Raised when a panel does not support a requested command."""


class UltraSyncDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manage a single UltraSync panel connection."""

    def __init__(self, hass: HomeAssistant, *, config: dict, options: dict) -> None:
        """Initialize the coordinator."""
        self.hub = ultrasync.UltraSync(
            user=config[CONF_USERNAME],
            pin=config[CONF_PIN],
            host=config[CONF_HOST],
        )
        self.areas: tuple[dict[str, Any], ...] = ()
        self.zones: tuple[dict[str, Any], ...] = ()
        self.outputs: tuple[dict[str, Any], ...] = ()
        self.history_data: tuple[dict[str, Any], ...] = ()
        self._io_lock = asyncio.Lock()
        self._area_delta: dict[int, int] = {}
        self._zone_delta: dict[int, int] = {}
        self._output_delta: dict[str, Any] = {}
        self._history_delta: dict[str, tuple[Any, ...]] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=options[CONF_SCAN_INTERVAL]),
        )

    async def _async_run_locked(self, func: Callable[[], _ResultT]) -> _ResultT:
        """Run blocking panel I/O without blocking Home Assistant."""
        async with self._io_lock:
            return await self.hass.async_add_executor_job(func)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the latest panel snapshot."""
        try:
            async with asyncio.timeout(10):
                details = await self._async_run_locked(
                    partial(self.hub.details, max_age_sec=0)
                )
        except TimeoutError as err:
            raise UpdateFailed("Timed out while polling the UltraSync panel") from err
        except Exception as err:
            raise UpdateFailed(f"Unable to poll the UltraSync panel: {err}") from err

        if not details:
            raise UpdateFailed("The UltraSync panel returned no data")

        self.areas = tuple(dict(item) for item in details.get("areas", ()))
        self.zones = tuple(dict(item) for item in details.get("zones", ()))
        self.outputs = tuple(dict(item) for item in details.get("outputs", ()))
        self.history_data = tuple(
            dict(item) for item in details.get("history_data", ())
        )

        response: dict[str, Any] = {}
        self._process_zone_updates(response)
        self._process_area_updates(response)
        self._process_output_updates(response)
        self._process_history_updates(response)
        return response

    def _process_zone_updates(self, response: dict[str, Any]) -> None:
        for zone in self.zones:
            bank = zone["bank"]
            if self._zone_delta.get(bank) != zone["sequence"]:
                self.hass.bus.async_fire(
                    "ultrasync_zone_update",
                    {
                        "sensor": bank + 1,
                        "name": zone["name"],
                        "status": zone["status"],
                    },
                )
                self._zone_delta[bank] = zone["sequence"]
            response[f"zone{bank + 1:02}_state"] = zone["status"]

    def _process_area_updates(self, response: dict[str, Any]) -> None:
        for area in self.areas:
            bank = area["bank"]
            if self._area_delta.get(bank) != area["sequence"]:
                self.hass.bus.async_fire(
                    "ultrasync_area_update",
                    {
                        "area": bank + 1,
                        "name": area["name"],
                        "status": area["status"],
                    },
                )
                self._area_delta[bank] = area["sequence"]
            response[f"area{bank + 1:02}_state"] = area["status"]

    def _process_output_updates(self, response: dict[str, Any]) -> None:
        for index, output in enumerate(self.outputs, start=1):
            name = output["name"]
            if self._output_delta.get(name) != output["state"]:
                self.hass.bus.async_fire(
                    "ultrasync_output_update",
                    {"name": name, "status": output["state"]},
                )
                self._output_delta[name] = output["state"]
            response[f"output{index}state"] = output["state"]

    def _process_history_updates(self, response: dict[str, Any]) -> None:
        for history in self.history_data:
            area_name = history["area_name"]
            value = (
                history.get("action"),
                history.get("user"),
                history.get("timestamp"),
            )
            sensor_id = f"history_name{area_name}state"
            response[sensor_id] = "{} by {} at {}".format(*value)
            if self._history_delta.get(area_name) != value:
                self.hass.bus.async_fire(
                    "ultrasync_history_update",
                    {
                        "name": area_name,
                        "status": value[0],
                        "user": value[1],
                        "timestamp": value[2],
                    },
                )
                self._history_delta[area_name] = value

    async def async_set_alarm(self, scene: str, area: int | None = None) -> None:
        """Set an alarm scene after checking panel capabilities."""
        if not self.hub.supports_alarm_scene(scene):
            raise UltraSyncUnsupportedError(
                f"{scene} is not supported by this {self.hub.vendor} panel"
            )
        result = await self._async_run_locked(
            partial(self.hub.set_alarm, areas=area, state=scene)
        )
        if not result:
            raise UltraSyncCommandError(f"The panel rejected the {scene} command")
        await self.async_request_refresh()

    async def async_set_zone_bypass(self, zone: int, state: bool) -> None:
        """Set zone bypass state."""
        result = await self._async_run_locked(
            partial(self.hub.set_zone_bypass, zone=zone, state=state)
        )
        if not result:
            raise UltraSyncCommandError(
                f"The panel rejected bypass={state} for zone {zone}"
            )
        await self.async_request_refresh()

    async def async_set_output(self, output: int, state: int) -> None:
        """Set an output state."""
        result = await self._async_run_locked(
            partial(self.hub.set_output_control, output=output, state=state)
        )
        if not result:
            raise UltraSyncCommandError(
                f"The panel rejected state={state} for output {output}"
            )
        await self.async_request_refresh()
