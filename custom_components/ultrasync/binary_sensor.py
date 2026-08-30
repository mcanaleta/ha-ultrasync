"""Binary sensor entities for UltraSync zones."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UltraSyncConfigEntry
from .entity import UltraSyncEntity

ACTIVE_ZONE_STATES = frozenset(
    {
        "alarm",
        "entry delay",
        "not ready",
        "test active",
    }
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UltraSyncConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one binary sensor for every panel zone."""
    coordinator = entry.runtime_data
    async_add_entities(
        UltraSyncZoneBinarySensor(coordinator, entry, zone["bank"])
        for zone in coordinator.zones
    )


class UltraSyncZoneBinarySensor(UltraSyncEntity, BinarySensorEntity):
    """Represent the active/clear state of an UltraSync zone."""

    _attr_device_class = BinarySensorDeviceClass.OPENING
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: UltraSyncConfigEntry, bank: int) -> None:
        super().__init__(coordinator, entry)
        self._bank = bank
        zone = self._current_zone
        self._attr_name = zone["name"] if zone else f"Zone {bank + 1}"
        self._attr_unique_id = f"{entry.entry_id}_zone_{bank + 1}"

    @property
    def _current_zone(self) -> dict[str, Any] | None:
        return next(
            (zone for zone in self.coordinator.zones if zone["bank"] == self._bank),
            None,
        )

    @property
    def is_on(self) -> bool | None:
        zone = self._current_zone
        if zone is None:
            return None
        return zone_is_active(zone)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        zone = self._current_zone
        if zone is None:
            return None
        return {
            "zone": self._bank + 1,
            "ultrasync_status": zone.get("status"),
            "can_bypass": zone.get("can_bypass"),
            "priority": zone.get("priority"),
        }


def zone_is_active(zone: dict[str, Any]) -> bool:
    """Return whether a zone represents an active opening or detector."""
    return str(zone.get("status", "")).casefold() in ACTIVE_ZONE_STATES
