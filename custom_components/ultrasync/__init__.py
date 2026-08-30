"""The Interlogix/Hills ComNav UltraSync Hub integration."""

from __future__ import annotations

from typing import cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from ultrasync import AlarmScene

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_AWAY,
    SERVICE_BYPASS,
    SERVICE_DISARM,
    SERVICE_FIRE,
    SERVICE_MEDICAL,
    SERVICE_PANIC,
    SERVICE_STAY,
    SERVICE_SWITCH,
    SERVICE_UNBYPASS,
)
from .coordinator import (
    UltraSyncCommandError,
    UltraSyncDataUpdateCoordinator,
    UltraSyncUnsupportedError,
)

PLATFORMS: tuple[Platform, ...] = (
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
)

UltraSyncConfigEntry = ConfigEntry[UltraSyncDataUpdateCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up integration-level UltraSync actions."""

    def loaded_coordinator() -> UltraSyncDataUpdateCoordinator:
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if len(entries) != 1:
            raise ServiceValidationError(
                "An UltraSync action requires exactly one loaded panel"
            )
        return cast(UltraSyncConfigEntry, entries[0]).runtime_data

    async def set_scene(call: ServiceCall, scene: str) -> None:
        try:
            await loaded_coordinator().async_set_alarm(scene)
        except (UltraSyncCommandError, UltraSyncUnsupportedError) as err:
            raise HomeAssistantError(str(err)) from err

    async def away(call: ServiceCall) -> None:
        await set_scene(call, AlarmScene.AWAY)

    async def stay(call: ServiceCall) -> None:
        await set_scene(call, AlarmScene.STAY)

    async def disarm(call: ServiceCall) -> None:
        await set_scene(call, AlarmScene.DISARMED)

    async def fire(call: ServiceCall) -> None:
        await set_scene(call, AlarmScene.FIRE)

    async def medical(call: ServiceCall) -> None:
        await set_scene(call, AlarmScene.MEDICAL)

    async def panic(call: ServiceCall) -> None:
        await set_scene(call, AlarmScene.PANIC)

    async def bypass(call: ServiceCall) -> None:
        try:
            await loaded_coordinator().async_set_zone_bypass(call.data["zone"], True)
        except (UltraSyncCommandError, UltraSyncUnsupportedError) as err:
            raise HomeAssistantError(str(err)) from err

    async def unbypass(call: ServiceCall) -> None:
        try:
            await loaded_coordinator().async_set_zone_bypass(call.data["zone"], False)
        except (UltraSyncCommandError, UltraSyncUnsupportedError) as err:
            raise HomeAssistantError(str(err)) from err

    async def switch(call: ServiceCall) -> None:
        try:
            await loaded_coordinator().async_set_output(
                call.data["output"], call.data["state"]
            )
        except (UltraSyncCommandError, UltraSyncUnsupportedError) as err:
            raise HomeAssistantError(str(err)) from err

    empty_schema = vol.Schema({})
    zone_schema = vol.Schema(
        {vol.Required("zone"): vol.All(vol.Coerce(int), vol.Range(min=1))}
    )
    output_schema = vol.Schema(
        {
            vol.Required("output"): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Required("state"): vol.All(vol.Coerce(int), vol.In((0, 1))),
        }
    )

    hass.services.async_register(DOMAIN, SERVICE_AWAY, away, schema=empty_schema)
    hass.services.async_register(DOMAIN, SERVICE_STAY, stay, schema=empty_schema)
    hass.services.async_register(DOMAIN, SERVICE_DISARM, disarm, schema=empty_schema)
    hass.services.async_register(DOMAIN, SERVICE_FIRE, fire, schema=empty_schema)
    hass.services.async_register(DOMAIN, SERVICE_MEDICAL, medical, schema=empty_schema)
    hass.services.async_register(DOMAIN, SERVICE_PANIC, panic, schema=empty_schema)
    hass.services.async_register(DOMAIN, SERVICE_BYPASS, bypass, schema=zone_schema)
    hass.services.async_register(DOMAIN, SERVICE_UNBYPASS, unbypass, schema=zone_schema)
    hass.services.async_register(DOMAIN, SERVICE_SWITCH, switch, schema=output_schema)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: UltraSyncConfigEntry) -> bool:
    """Set up UltraSync from a config entry."""
    if not entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={
                CONF_SCAN_INTERVAL: entry.data.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                )
            },
        )

    coordinator = UltraSyncDataUpdateCoordinator(
        hass,
        config=entry.data,
        options=entry.options,
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: UltraSyncConfigEntry) -> bool:
    """Unload an UltraSync config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: UltraSyncConfigEntry
) -> None:
    """Reload the entry after its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
