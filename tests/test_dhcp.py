"""DHCP recovery tests using Home Assistant's real flow manager, without I/O."""

import unittest
from contextlib import ExitStack
from tempfile import TemporaryDirectory
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import loader
from homeassistant.config_entries import (
    SOURCE_DHCP, SOURCE_IGNORE, SOURCE_USER, ConfigEntries, ConfigEntry,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

import custom_components
from custom_components.ultrasync import config_flow, _async_update_listener
from custom_components.ultrasync.alarm_control_panel import UltraSyncAlarmControlPanel
from custom_components.ultrasync.binary_sensor import UltraSyncZoneBinarySensor
from custom_components.ultrasync.discovery import dhcp_host, normalize_mac
from custom_components.ultrasync.sensor import UltraSyncLegacySensor

MAC = "00:0d:16:12:34:56"
OLD_HOST = "192.168.1.45"
HOST = "192.168.1.112"
INFO = DhcpServiceInfo(ip=HOST, hostname="panel", macaddress="000D16123456")


class DhcpFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.hass = HomeAssistant(self.directory.name)
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        await self.hass.config_entries.async_initialize()
        self.patches = ExitStack()
        integration = loader.Integration.resolve_from_root(
            self.hass, custom_components, "ultrasync"
        )
        self.patches.enter_context(patch.object(
            loader, "async_get_custom_components",
            AsyncMock(return_value={"ultrasync": integration}),
        ))
        self.patches.enter_context(patch(
            "homeassistant.config_entries.async_process_deps_reqs", AsyncMock()
        ))
        self.patches.enter_context(patch.object(
            self.hass.config_entries, "async_setup", AsyncMock(return_value=True)
        ))
        self.reload = self.patches.enter_context(patch.object(
            self.hass.config_entries, "async_reload", AsyncMock(return_value=True)
        ))
        # DHCP must never try credentials or issue panel commands itself.
        self.panel = self.patches.enter_context(patch.object(
            config_flow.ultrasync, "UltraSync"
        ))

    async def asyncTearDown(self):
        await self.hass.async_block_till_done()
        await self.hass.async_stop(force=True)
        self.patches.close()
        self.directory.cleanup()

    async def existing(self, **kwargs):
        fields = dict(
            domain="ultrasync", title="Original panel", version=1, minor_version=1,
            source=SOURCE_USER, unique_id=None,
            data={"host": OLD_HOST, "username": "test", "pin": "test-only", "extra": 7},
            options={"scan_interval": 5, "mac": MAC, "extra_option": True},
            discovery_keys=MappingProxyType({}), subentries_data=[],
        )
        fields.update(kwargs)
        entry = ConfigEntry(**fields)
        await self.hass.config_entries.async_add(entry)
        entry.add_update_listener(_async_update_listener)
        return entry

    async def dhcp(self, info=INFO):
        return await self.hass.config_entries.flow.async_init(
            "ultrasync", context={"source": SOURCE_DHCP}, data=info
        )

    async def test_ip_change_preserves_credentials_entities_and_device(self):
        entry = await self.existing()
        device_registry.async_setup(self.hass)
        await device_registry.async_load(self.hass)
        devices = device_registry.async_get(self.hass)
        registry = entity_registry.async_get(self.hass)
        await registry.async_load()
        coordinator = MagicMock(hass=self.hass, config_entry=entry)
        coordinator.areas = [{"bank": 0, "name": "Area"}]
        coordinator.zones = [{"bank": 0, "name": "Zone"}]

        def entities():
            return [
                UltraSyncAlarmControlPanel(coordinator, entry, 0),
                UltraSyncZoneBinarySensor(coordinator, entry, 0),
                UltraSyncLegacySensor(coordinator, entry, "zone01_state", "Zone", lambda: {}),
            ]

        original = entities()
        device = devices.async_get_or_create(
            config_entry_id=entry.entry_id, **original[0].device_info
        )
        registered = [registry.async_get_or_create(
            domain, "ultrasync", entity.unique_id, config_entry=entry,
            device_id=device.id, suggested_object_id=f"original_{index}",
        ) for index, (domain, entity) in enumerate(zip(
            ["alarm_control_panel", "binary_sensor", "sensor"], original, strict=True
        ))]
        old_data, old_options = dict(entry.data), dict(entry.options)
        result = await self.dhcp()
        await self.hass.async_block_till_done()
        self.assertEqual(result["reason"], "already_configured")
        self.assertEqual(entry.data, {**old_data, "host": HOST})
        self.assertEqual(entry.options, old_options)
        self.assertEqual(entry.title, "Original panel")
        self.assertIsNone(entry.unique_id)
        self.assertEqual([e.unique_id for e in entities()], [e.unique_id for e in original])
        self.assertEqual(entities()[0].device_info["connections"], {("mac", MAC)})
        self.assertEqual(devices.async_get_or_create(
            config_entry_id=entry.entry_id, **entities()[0].device_info
        ).id, device.id)
        for item in registered:
            self.assertIs(registry.async_get(item.entity_id), item)
        self.reload.assert_awaited_once_with(entry.entry_id)
        self.panel.assert_not_called()
        # Repeated discovery must not reload again.
        await self.dhcp()
        await self.hass.async_block_till_done()
        self.reload.assert_awaited_once()

    async def test_unbound_unknown_ignored_and_invalid_events_do_nothing(self):
        entry = await self.existing()
        for changes, info in [
            ({"options": {"scan_interval": 5}}, INFO),
            ({"options": {"mac": "00:0d:16:65:43:21"}}, INFO),
            ({"options": {"mac": MAC}}, DhcpServiceInfo(ip=HOST, hostname="", macaddress="invalid")),
        ]:
            self.hass.config_entries.async_update_entry(entry, **changes)
            await self.hass.async_block_till_done()
            self.reload.reset_mock()
            before = dict(entry.data), dict(entry.options)
            result = await self.dhcp(info)
            await self.hass.async_block_till_done()
            self.assertEqual(result["reason"], "not_configured")
            self.assertEqual((dict(entry.data), dict(entry.options)), before)
            self.reload.assert_not_awaited()
        self.panel.assert_not_called()

    async def test_ignored_panel_stays_ignored(self):
        entry = await self.existing(source=SOURCE_IGNORE)
        before = dict(entry.data)
        result = await self.dhcp()
        await self.hass.async_block_till_done()
        self.assertEqual(result["reason"], "not_configured")
        self.assertEqual(dict(entry.data), before)
        self.reload.assert_not_awaited()
        self.panel.assert_not_called()

    async def test_data_mac_and_url_endpoint_are_supported(self):
        entry = await self.existing(
            data={"host": f"https://{OLD_HOST}:8080/panel?x=1", "mac": MAC},
            options={"scan_interval": 5},
        )
        await self.dhcp()
        self.assertEqual(entry.data["host"], f"https://{HOST}:8080/panel?x=1")
        self.panel.assert_not_called()

    async def test_options_bind_and_clear_mac_preserving_other_options(self):
        entry = await self.existing()
        for mac in ["00-0D-16-12-34-56", ""]:
            result = await self.hass.config_entries.options.async_init(entry.entry_id)
            schema = result["data_schema"]
            invalid = await self.hass.config_entries.options.async_configure(
                result["flow_id"], {"mac": "bad-mac"}
            )
            self.assertEqual(invalid["errors"], {"mac": "invalid_mac"})
            result = await self.hass.config_entries.options.async_configure(
                result["flow_id"], schema({"scan_interval": 9, "mac": mac})
            )
            self.assertEqual(result["type"], "create_entry")
            self.assertEqual(entry.options["mac"], normalize_mac(mac))
            self.assertTrue(entry.options["extra_option"])
        before = dict(entry.data)
        await self.dhcp()
        self.assertEqual(dict(entry.data), before)
        self.panel.assert_not_called()

    async def test_manual_setup_remains_available_without_mac(self):
        result = await self.hass.config_entries.flow.async_init(
            "ultrasync", context={"source": SOURCE_USER}
        )
        data = result["data_schema"]({
            "host": HOST, "username": "test", "pin": "test-only"
        })
        self.assertNotIn("mac", data)
        self.panel.return_value.login.return_value = True
        result = await self.hass.config_entries.flow.async_configure(result["flow_id"], data)
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["host"], HOST)

    async def test_manifest_registers_only_known_devices(self):
        matchers = await loader.async_get_dhcp(self.hass)
        self.assertEqual(
            [matcher for matcher in matchers if matcher["domain"] == "ultrasync"],
            [{"domain": "ultrasync", "registered_devices": True}],
        )


@pytest.mark.parametrize(("old", "new", "expected"), [
    (OLD_HOST, HOST, HOST),
    (f"http://{OLD_HOST}:81/path?q=1#x", HOST, f"http://{HOST}:81/path?q=1#x"),
    (f"https://user:secret@{OLD_HOST}/", HOST, f"https://user:secret@{HOST}/"),
    ("alarm.local", HOST, "alarm.local"),
    ("https://alarm.local:81/", HOST, "https://alarm.local:81/"),
    (OLD_HOST, "127.0.0.1", OLD_HOST),
    (OLD_HOST, "224.1.1.1", OLD_HOST),
    (OLD_HOST, "0.0.0.0", OLD_HOST),
    (OLD_HOST, "::1", OLD_HOST),
    (OLD_HOST, "invalid", OLD_HOST),
])
def test_endpoint_replacement(old, new, expected):
    assert dhcp_host(old, new) == expected
