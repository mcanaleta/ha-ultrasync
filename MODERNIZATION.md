# UltraSync modernization beta

This branch is the first compatibility-focused modernization of the UltraSync
Home Assistant integration.

## Included

- Native `alarm_control_panel` entities for all detected areas.
- Native `binary_sensor` entities for all detected zones.
- Existing state sensors and UltraSync actions remain available.
- Blocking HTTP calls run in Home Assistant's executor behind a shared lock.
- Runtime state is stored in `ConfigEntry.runtime_data`.
- First refresh uses `async_config_entry_first_refresh()`.
- Panel capability checks prevent unsupported emergency scenes from falling
  back to a disarm command.
- History events are emitted only when the history item changes.

## Zone binary sensors

Zones default to the generic `opening` device class because UltraSync does not
reliably report whether a zone is a PIR, door, or window. Home Assistant users
can change **Show as** for individual entities to Motion, Door, Window, or
another appropriate class.

The binary sensor is active for `Not Ready`, `Alarm`, `Entry Delay`, and
`Test Active`. Diagnostic conditions such as tamper and low battery remain in
the `ultrasync_status` attribute for this beta.

## Compatibility

The old sensor unique IDs are preserved. New native entities use separate
unique IDs, so dashboards and automations can be migrated gradually.

This is a beta. Back up Home Assistant before replacing the existing custom
integration and do not test emergency actions on a live security panel.
