"""Config flow for the Interlogix/Hills ComNav UltraSync Hub."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_MAC,
    CONF_NAME,
    CONF_PIN,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.typing import ConfigType

import ultrasync

from .const import (
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,  # pylint: disable=unused-import
)
from .discovery import configured_mac, dhcp_host, normalize_mac

_LOGGER = logging.getLogger(__name__)


class AuthFailureException(IOError):
    """A general exception we can use to track Authentication failures."""


def validate_input(hass: HomeAssistant, data: dict) -> dict[str, Any]:
    """Validate the user input allows us to connect."""

    usync = ultrasync.UltraSync(
        host=data[CONF_HOST], user=data[CONF_USERNAME], pin=data[CONF_PIN]
    )

    # validate by attempting to authenticate with our hub

    if not usync.login():
        # report our connection issue
        raise AuthFailureException()

    return True


class UltraSyncConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """UltraSync config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return UltraSyncOptionsFlowHandler(config_entry)

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo):
        """Recover an existing panel's IPv4 address using its bound MAC."""
        try:
            mac = normalize_mac(discovery_info.macaddress)
        except vol.Invalid:
            return self.async_abort(reason="not_configured")
        for entry in self._async_current_entries():
            if (
                entry.source == config_entries.SOURCE_IGNORE
                or not mac
                or configured_mac(entry) != mac
            ):
                continue
            host = dhcp_host(entry.data[CONF_HOST], discovery_info.ip)
            if host != entry.data[CONF_HOST]:
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_HOST: host}
                )
            return self.async_abort(reason="already_configured")
        return self.async_abort(reason="not_configured")

    async def async_step_user(
        self, user_input: ConfigType | None = None
    ) -> dict[str, Any]:
        """Handle user flow."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors = {}

        if user_input is not None:
            try:
                if CONF_MAC in user_input:
                    user_input = {
                        **user_input, CONF_MAC: normalize_mac(user_input[CONF_MAC])
                    }
                await self.hass.async_add_executor_job(
                    validate_input, self.hass, user_input
                )

            except vol.Invalid:
                errors[CONF_MAC] = "invalid_mac"

            except AuthFailureException:
                errors["base"] = "cannot_connect"

            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                return self.async_abort(reason="unknown")
            else:
                return self.async_create_entry(
                    title=user_input[CONF_HOST],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PIN): str,
                    vol.Optional(CONF_MAC): str,
                }
            ),
            errors=errors,
        )


class UltraSyncOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle UltraSync client options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.entry = config_entry

    async def async_step_init(self, user_input: ConfigType | None = None):
        """Manage UltraSync options."""
        errors = {}
        if user_input is not None:
            try:
                if CONF_MAC in user_input:
                    user_input = {
                        **user_input, CONF_MAC: normalize_mac(user_input[CONF_MAC])
                    }
            except vol.Invalid:
                errors[CONF_MAC] = "invalid_mac"
            else:
                return self.async_create_entry(
                    title="", data={**self.entry.options, **user_input}
                )

        options = {
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=self.entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                ),
            ): int,
            vol.Optional(CONF_MAC, default=configured_mac(self.entry)): str,
        }

        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(options), errors=errors
        )
