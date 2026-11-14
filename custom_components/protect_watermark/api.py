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
from http import HTTPStatus
import re
from typing import Any, cast

from uiprotect import ProtectApiClient
from uiprotect.exceptions import BadRequest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import PROTECT_DOMAIN


class ProtectUnavailableError(Exception):
    """The UniFi Protect config entry isn't loaded."""


class ProtectPublicOnlyError(Exception):
    """The UniFi Protect integration has no private API access."""


@dataclass(slots=True, frozen=True)
class OverlayCamera:
    """An adopted Protect camera."""

    id: str
    mac: str
    name: str
    # Only used to explain why a camera has no watermark entities.
    model: str | None = None
    firmware: str | None = None


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
        OverlayCamera(
            id=camera.id,
            mac=camera.mac,
            name=camera.name or camera.mac,
            model=camera.market_name,
            firmware=camera.firmware_version,
        )
        for camera in api.bootstrap.cameras.values()
        if camera.is_adopted_by_us
    ]


def protect_version(api: ProtectApiClient) -> str:
    """Return the console's UniFi Protect version."""
    return str(api.bootstrap.nvr.version)


# uiprotect puts the HTTP status only in the message of the errors it raises.
_STATUS = re.compile(r"Status: (\d{3})")


def overlay_unsupported(err: BadRequest) -> bool:
    """Return whether an overlay read failed because the API isn't there.

    Protect answers 400 for a camera without the overlay API, and a version
    without the route answers 404. ``uiprotect`` raises ``BadRequest`` for
    every other 4xx too (a camera that's updating, for one), and those
    shouldn't be read as the camera lacking the watermark. An error without a
    status didn't come from Protect's answer, so it's taken as unsupported.
    """
    if (match := _STATUS.search(str(err))) is None:
        return True
    return int(match.group(1)) in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND)


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


async def patch_overlay(
    api: ProtectApiClient, camera_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Change a camera's overlay settings and return the new settings.

    The per-camera route merges the body into the stored settings, so only the
    given keys change. A corner set to ``None`` is cleared. ``preview: false``
    saves the change instead of showing a temporary preview.
    """
    data = await api.api_request(
        f"cameras/{camera_id}/overlay-settings",
        method="patch",
        json={**changes, "preview": False},
    )
    settings = data.get("settings") if isinstance(data, dict) else None
    if not isinstance(settings, dict):
        raise TypeError(f"Unexpected overlay response for camera {camera_id}")
    return cast("dict[str, Any]", settings)
