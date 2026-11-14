"""A repair issue for when no camera supports the visible watermark."""

from __future__ import annotations

from awesomeversion import AwesomeVersion
from awesomeversion.exceptions import AwesomeVersionException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .api import OverlayCamera
from .const import (
    DOMAIN,
    ISSUE_NO_SUPPORTED_CAMERAS,
    MIN_CAMERA_FIRMWARE,
    MIN_PROTECT_VERSION,
)

LEARN_MORE_URL = "https://github.com/KB1RMA/ha-protect-watermark#requirements"


def issue_id(key: str, entry: ConfigEntry) -> str:
    """Return the ID of a config entry's repair issue."""
    return f"{key}_{entry.entry_id}"


@callback
def async_update_support_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    protect_version: str,
    any_supported: bool,
    unsupported: list[OverlayCamera],
) -> None:
    """Raise the issue when Protect has cameras but none support the watermark.

    It's cleared once a camera supports it. With no adopted cameras at all,
    there's nothing to explain, so no issue is raised.
    """
    key = issue_id(ISSUE_NO_SUPPORTED_CAMERAS, entry)
    if any_supported or not unsupported:
        ir.async_delete_issue(hass, DOMAIN, key)
        return
    protect_too_old = bool(is_older(protect_version, MIN_PROTECT_VERSION))
    ir.async_create_issue(
        hass,
        DOMAIN,
        key,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        learn_more_url=LEARN_MORE_URL,
        translation_key=ISSUE_NO_SUPPORTED_CAMERAS,
        translation_placeholders={
            "console": entry.title,
            "min_protect_version": MIN_PROTECT_VERSION,
            "min_firmware": MIN_CAMERA_FIRMWARE,
            "protect_version": describe_protect(protect_version),
            "cameras": "\n".join(
                f"- {describe_camera(camera, protect_too_old=protect_too_old)}"
                for camera in unsupported
            ),
        },
    )


def is_older(version: str | None, minimum: str) -> bool | None:
    """Return whether a version is older than the minimum, or None if unknown."""
    if not version:
        return None
    try:
        return AwesomeVersion(version) < AwesomeVersion(minimum)
    except AwesomeVersionException:
        return None


def describe_protect(version: str) -> str:
    """Describe the Protect version against the minimum."""
    if is_older(version, MIN_PROTECT_VERSION):
        return f"{version}, older than {MIN_PROTECT_VERSION}"
    return version


def describe_camera(camera: OverlayCamera, *, protect_too_old: bool = False) -> str:
    """Describe why a camera may not support the watermark.

    Protect only says a camera turned the overlay down, not why. An old
    Protect explains it for every camera, so the camera isn't judged then.
    Old firmware may be the cause, but some models never get the watermark
    whatever their firmware, so both are named.
    """
    name = f"{camera.name} ({camera.model})" if camera.model else camera.name
    firmware = camera.firmware or "unknown"
    if protect_too_old:
        return f"{name}: firmware {firmware}"
    older = is_older(camera.firmware, MIN_CAMERA_FIRMWARE)
    if older:
        return (
            f"{name}: firmware {firmware} is older than {MIN_CAMERA_FIRMWARE}, "
            "or this model doesn't support it"
        )
    if older is None:
        return f"{name}: firmware {firmware}, not supported by Protect"
    return f"{name}: firmware {firmware}, this model doesn't support it"
