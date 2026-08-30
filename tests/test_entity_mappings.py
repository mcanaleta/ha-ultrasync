"""Tests for native Home Assistant entity state mappings."""

import asyncio

import pytest
from homeassistant.components.alarm_control_panel import AlarmControlPanelState
from ultrasync import AlarmScene

from custom_components.ultrasync.alarm_control_panel import alarm_state_from_area
from custom_components.ultrasync.binary_sensor import zone_is_active
from custom_components.ultrasync.coordinator import (
    UltraSyncDataUpdateCoordinator,
    UltraSyncUnsupportedError,
)


@pytest.mark.parametrize(
    ("area", "expected"),
    (
        ({"status": "Ready"}, AlarmControlPanelState.DISARMED),
        ({"status": "Not Ready"}, AlarmControlPanelState.DISARMED),
        ({"status": "Armed Away"}, AlarmControlPanelState.ARMED_AWAY),
        ({"status": "Armed Stay"}, AlarmControlPanelState.ARMED_HOME),
        ({"status": "Exit Delay 1"}, AlarmControlPanelState.ARMING),
        ({"status": "Entry Delay"}, AlarmControlPanelState.PENDING),
        ({"status": "Burglar Alarm"}, AlarmControlPanelState.TRIGGERED),
        (
            {"status": "Sensor Trouble", "states": {"armed": True}},
            AlarmControlPanelState.ARMED_AWAY,
        ),
        (
            {"status": "Sensor Bypass", "states": {"partial": True}},
            AlarmControlPanelState.ARMED_HOME,
        ),
    ),
)
def test_alarm_state_mapping(area, expected):
    assert alarm_state_from_area(area) is expected


@pytest.mark.parametrize("status", ("Not Ready", "Alarm", "Entry Delay", "Test Active"))
def test_active_zone_states(status):
    assert zone_is_active({"status": status}) is True


@pytest.mark.parametrize(
    "status",
    ("Ready", "Tamper", "Trouble", "Low Battery", "Supervision Fault"),
)
def test_inactive_or_diagnostic_zone_states(status):
    assert zone_is_active({"status": status}) is False


def test_coordinator_rejects_unsupported_scene_before_io():
    """Capability validation must happen before any command is scheduled."""

    class UnsupportedPanel:
        vendor = "xgen8"

        @staticmethod
        def supports_alarm_scene(scene):
            return False

    coordinator = object.__new__(UltraSyncDataUpdateCoordinator)
    coordinator.hub = UnsupportedPanel()

    with pytest.raises(UltraSyncUnsupportedError):
        asyncio.run(coordinator.async_set_alarm(AlarmScene.FIRE))
