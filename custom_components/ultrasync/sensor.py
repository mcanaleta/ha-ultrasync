"""Legacy UltraSync state sensors kept for backwards compatibility."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UltraSyncConfigEntry
from .const import DEFAULT_NAME
from .entity import UltraSyncEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UltraSyncConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the existing text sensors without dispatcher-based discovery."""
    coordinator = entry.runtime_data
    prefix = entry.data.get(CONF_NAME, DEFAULT_NAME)
    entities: list[UltraSyncLegacySensor] = []

    for area in coordinator.areas:
        bank = area["bank"]
        entities.append(
            UltraSyncLegacySensor(
                coordinator,
                entry,
                f"area{bank + 1:02}_state",
                f"{prefix} Area{bank + 1}State",
                lambda bank=bank: _find_by_bank(coordinator.areas, bank),
            )
        )

    for zone in coordinator.zones:
        bank = zone["bank"]
        entities.append(
            UltraSyncLegacySensor(
                coordinator,
                entry,
                f"zone{bank + 1:02}_state",
                f"{prefix} Zone{bank + 1}State",
                lambda bank=bank: _find_by_bank(coordinator.zones, bank),
            )
        )

    for index, output in enumerate(coordinator.outputs, start=1):
        entities.append(
            UltraSyncLegacySensor(
                coordinator,
                entry,
                f"output{index}state",
                f"{prefix} Output{index}State",
                lambda index=index: _find_output(coordinator.outputs, index),
            )
        )

    for history in coordinator.history_data:
        area_name = history["area_name"]
        entities.append(
            UltraSyncLegacySensor(
                coordinator,
                entry,
                f"history_name{area_name}state",
                f"{prefix} History {area_name} State",
                lambda area_name=area_name: _find_history(
                    coordinator.history_data, area_name
                ),
            )
        )

    async_add_entities(entities)


def _find_by_bank(items, bank: int) -> dict[str, Any] | None:
    return next((item for item in items if item["bank"] == bank), None)


def _find_output(items, index: int) -> dict[str, Any] | None:
    return items[index - 1] if len(items) >= index else None


def _find_history(items, area_name: str) -> dict[str, Any] | None:
    return next((item for item in items if item["area_name"] == area_name), None)


class UltraSyncLegacySensor(UltraSyncEntity, SensorEntity):
    """Expose the old text state while users migrate automations."""

    def __init__(
        self,
        coordinator,
        entry: UltraSyncConfigEntry,
        sensor_type: str,
        name: str,
        metadata: Callable[[], dict[str, Any] | None],
    ) -> None:
        super().__init__(coordinator, entry)
        self._sensor_type = sensor_type
        self._metadata = metadata
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"

    @property
    def native_value(self) -> Any:
        return self.coordinator.data.get(self._sensor_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self._metadata()
