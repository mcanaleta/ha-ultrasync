"""Native alarm control panel entities for UltraSync areas."""

from __future__ import annotations

from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ultrasync import AlarmScene

from . import UltraSyncConfigEntry
from .coordinator import UltraSyncCommandError
from .entity import UltraSyncEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UltraSyncConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one alarm entity for every panel area."""
    coordinator = entry.runtime_data
    async_add_entities(
        UltraSyncAlarmControlPanel(coordinator, entry, area["bank"])
        for area in coordinator.areas
    )


class UltraSyncAlarmControlPanel(UltraSyncEntity, AlarmControlPanelEntity):
    """Control and report one UltraSync area."""

    _attr_code_arm_required = False
    _attr_code_disarm_required = False
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: UltraSyncConfigEntry, bank: int) -> None:
        super().__init__(coordinator, entry)
        self._bank = bank
        area = self._current_area
        self._attr_name = area["name"] if area else f"Area {bank + 1}"
        self._attr_unique_id = f"{entry.entry_id}_alarm_area_{bank + 1}"

    @property
    def _current_area(self) -> dict[str, Any] | None:
        return next(
            (area for area in self.coordinator.areas if area["bank"] == self._bank),
            None,
        )

    @property
    def supported_features(self) -> AlarmControlPanelEntityFeature:
        features = AlarmControlPanelEntityFeature(0)
        if self.coordinator.hub.supports_alarm_scene(AlarmScene.STAY):
            features |= AlarmControlPanelEntityFeature.ARM_HOME
        if self.coordinator.hub.supports_alarm_scene(AlarmScene.AWAY):
            features |= AlarmControlPanelEntityFeature.ARM_AWAY
        return features

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        area = self._current_area
        if area is None:
            return None

        return alarm_state_from_area(area)

    async def _async_set_scene(self, scene: str) -> None:
        try:
            await self.coordinator.async_set_alarm(scene, self._bank + 1)
        except UltraSyncCommandError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        await self._async_set_scene(AlarmScene.DISARMED)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        await self._async_set_scene(AlarmScene.STAY)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self._async_set_scene(AlarmScene.AWAY)


def alarm_state_from_area(area: dict[str, Any]) -> AlarmControlPanelState:
    """Map an UltraSync area snapshot to a Home Assistant alarm state."""
    status = str(area.get("status", "")).casefold()
    states = area.get("states", {})
    if "alarm" in status:
        return AlarmControlPanelState.TRIGGERED
    if "entry delay" in status:
        return AlarmControlPanelState.PENDING
    if "exit delay" in status:
        return AlarmControlPanelState.ARMING
    if states.get("armed") or status.startswith("armed away"):
        return AlarmControlPanelState.ARMED_AWAY
    if states.get("partial") or status.startswith("armed stay"):
        return AlarmControlPanelState.ARMED_HOME
    return AlarmControlPanelState.DISARMED
