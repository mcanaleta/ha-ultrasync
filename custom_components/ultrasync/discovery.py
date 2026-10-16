"""Stable network identity and endpoint handling for DHCP discovery."""

from ipaddress import IPv4Address
import re
from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant.const import CONF_MAC
from homeassistant.helpers.device_registry import format_mac


def normalize_mac(value: str) -> str:
    """Validate an optional MAC address and use Home Assistant's format."""
    value = value.strip()
    if not value:
        return ""
    if not re.fullmatch(
        r"(?:[0-9a-fA-F]{12}|(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}"
        r"|(?:[0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2})", value
    ):
        raise vol.Invalid("Invalid MAC address")
    return format_mac(value)


def configured_mac(entry) -> str:
    """Get the explicitly bound MAC, allowing options to clear it."""
    return normalize_mac(entry.options.get(CONF_MAC, entry.data.get(CONF_MAC, "")))


def dhcp_host(host: str, address: str) -> str:
    """Replace an IPv4 endpoint, preserving URLs and configured DNS names."""
    try:
        new_ip = IPv4Address(address)
        if new_ip.is_unspecified or new_ip.is_loopback or new_ip.is_multicast:
            return host
        has_scheme = "://" in host
        parts = urlsplit(host if has_scheme else "//" + host)
        IPv4Address(parts.hostname)
        port = parts.port
    except (ValueError, TypeError):
        return host
    userinfo, separator, _ = parts.netloc.rpartition("@")
    netloc = (userinfo + separator if separator else "") + str(new_ip)
    if port is not None:
        netloc += f":{port}"
    result = parts._replace(netloc=netloc).geturl()
    return result if has_scheme else result.removeprefix("//")
