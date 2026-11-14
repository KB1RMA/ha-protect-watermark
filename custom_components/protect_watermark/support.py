"""A repair issue for when no camera supports the visible watermark."""

from __future__ import annotations

from awesomeversion import AwesomeVersion
from awesomeversion.exceptions import AwesomeVersionException
from uiprotect import ProtectApiClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .api import OverlayCamera, protect_version
from .const import (
    DOMAIN,
    ISSUE_NO_SUPPORTED_CAMERAS,
    MIN_CAMERA_FIRMWARE,
    MIN_PROTECT_VERSION,
)

LEARN_MORE_URL = "https://github.com/KB1RMA/ha-protect-watermark#requirements"


def issue_id(entry: ConfigEntry) -> str:
    """Return the repair issue ID for a config entry."""
    return f"{ISSUE_NO_SUPPORTED_CAMERAS}_{entry.entry_id}"


@callback
def async_update_support_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
    api: ProtectApiClient,
    *,
    any_supported: bool,
    unsupported: list[OverlayCamera],
) -> None:
    """Raise the issue when Protect has cameras but none support the watermark.

    It's cleared once a camera supports it. With no adopted cameras at all,
    there's nothing to explain, so no issue is raised.
    """
    if any_supported or not unsupported:
        ir.async_delete_issue(hass, DOMAIN, issue_id(entry))
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id(entry),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        learn_more_url=LEARN_MORE_URL,
        translation_key=ISSUE_NO_SUPPORTED_CAMERAS,
        translation_placeholders={
            "console": entry.title,
            "min_protect_version": MIN_PROTECT_VERSION,
            "min_firmware": MIN_CAMERA_FIRMWARE,
            "protect_version": describe_protect(protect_version(api)),
            "cameras": "\n".join(
                f"- {describe_camera(camera)}" for camera in unsupported
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


def describe_camera(camera: OverlayCamera) -> str:
    """Describe why a camera may not support the watermark.

    Old firmware is named as the likely cause. Otherwise the model itself
    doesn't support it, since Protect turned down a camera on new enough
    firmware.
    """
    name = f"{camera.name} ({camera.model})" if camera.model else camera.name
    older = is_older(camera.firmware, MIN_CAMERA_FIRMWARE)
    if older:
        return f"{name}: firmware {camera.firmware}, older than {MIN_CAMERA_FIRMWARE}"
    if older is None:
        firmware = camera.firmware or "unknown"
        return f"{name}: firmware {firmware}, not supported by Protect"
    return f"{name}: firmware {camera.firmware}, this model doesn't support it"
