"""Base entity for UltraSync platforms."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import UltraSyncDataUpdateCoordinator


class UltraSyncEntity(CoordinatorEntity[UltraSyncDataUpdateCoordinator]):
    """Base class shared by UltraSync entities."""

    def __init__(self, coordinator: UltraSyncDataUpdateCoordinator, entry) -> None:
        """Initialize a panel entity."""
        super().__init__(coordinator)
        version = getattr(coordinator.hub, "version", None)
        release = getattr(coordinator.hub, "release", None)
        sw_version = ".".join(str(value) for value in (version, release) if value)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or entry.data.get("name", DEFAULT_NAME),
            manufacturer="Interlogix / Hills / UltraSync",
            model=str(getattr(coordinator.hub, "vendor", "UltraSync")),
            sw_version=sw_version or None,
        )
