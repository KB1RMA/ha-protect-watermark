"""Access to Protect's overlay settings through the UniFi Protect integration's client.

This integration has no sign-in of its own. It finds the loaded config entry of
Home Assistant's UniFi Protect integration and borrows its ``uiprotect``
``ProtectApiClient`` (``entry.runtime_data.api``), which already handles
sign-in, CSRF tokens and re-login.

The overlay ("Visible Watermark" in Protect's Evidence Trust settings) is only
on Protect's private API, at ``/proxy/protect/api/cameras/{id}/overlay-settings``.
It isn't in the public Integration API as of Protect 7.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from uiprotect import ProtectApiClient

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import PROTECT_DOMAIN


class ProtectUnavailableError(Exception):
    """The UniFi Protect config entry isn't loaded."""


class ProtectPublicOnlyError(Exception):
    """The UniFi Protect integration has no private API access."""


@dataclass(slots=True, frozen=True)
class OverlayCamera:
    """A camera that supports the overlay API."""

    id: str
    mac: str
    name: str


def get_protect_client(hass: HomeAssistant, protect_entry_id: str) -> ProtectApiClient:
    """Return the signed-in client of a loaded UniFi Protect config entry.

    Looked up on every call, because the UniFi Protect integration replaces
    its client when its entry reloads.
    """
    entry = hass.config_entries.async_get_entry(protect_entry_id)
    if (
        entry is None
        or entry.domain != PROTECT_DOMAIN
        or entry.state is not ConfigEntryState.LOADED
    ):
        raise ProtectUnavailableError(protect_entry_id)
    # The UniFi Protect integration keeps a ``ProtectData`` in ``runtime_data``,
    # with its client in ``.api``. That isn't a public Home Assistant
    # interface, so check what is there rather than trusting it.
    data = getattr(entry, "runtime_data", None)
    api = getattr(data, "api", None)
    if not isinstance(api, ProtectApiClient):
        raise ProtectUnavailableError(protect_entry_id)
    if api.is_public_only:
        raise ProtectPublicOnlyError(protect_entry_id)
    return api


def adopted_cameras(api: ProtectApiClient) -> list[OverlayCamera]:
    """Return the adopted cameras from the Protect integration's bootstrap."""
    return [
        OverlayCamera(id=camera.id, mac=camera.mac, name=camera.name or camera.mac)
        for camera in api.bootstrap.cameras.values()
        if camera.is_adopted_by_us
    ]


async def get_overlay(api: ProtectApiClient, camera_id: str) -> dict[str, Any]:
    """Get a camera's overlay settings.

    Protect answers 400 ("Camera does not support the overlay API") for
    cameras that only have the older OSD settings. ``uiprotect`` raises
    ``BadRequest`` for that.
    """
    data = await api.api_request(f"cameras/{camera_id}/overlay-settings")
    if not isinstance(data, dict):
        raise TypeError(f"Unexpected overlay settings for camera {camera_id}")
    return data


async def set_corner(
    api: ProtectApiClient, camera_id: str, corner: str, content: str | None
) -> dict[str, Any]:
    """Set one corner of a camera's overlay and return the new settings.

    The per-camera route merges the body into the stored settings, so only the
    given corner changes. ``None`` clears the corner. ``preview: false`` saves
    the change instead of showing a temporary preview.
    """
    value: dict[str, Any] | None = None if content is None else {"content": content}
    data = await api.api_request(
        f"cameras/{camera_id}/overlay-settings",
        method="patch",
        json={corner: value, "preview": False},
    )
    settings = data.get("settings") if isinstance(data, dict) else None
    if not isinstance(settings, dict):
        raise TypeError(f"Unexpected overlay response for camera {camera_id}")
    return cast("dict[str, Any]", settings)
