"""A repair issue for when no camera supports the visible watermark."""

from __future__ import annotations

from collections.abc import Iterable
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .api import OverlayCamera, is_older
from .const import (
    DOMAIN,
    ISSUE_NO_SUPPORTED_CAMERAS,
    MIN_CAMERA_FIRMWARE,
    MIN_PROTECT_VERSION,
)

LEARN_MORE_URL = "https://github.com/KB1RMA/ha-protect-watermark#requirements"

# Characters that would format a camera's name in the issue's Markdown.
_MARKDOWN = re.compile(r"([\\`*_\[\]<>#|~])")


def issue_id(key: str, entry: ConfigEntry) -> str:
    """Return the ID of a config entry's repair issue."""
    return f"{key}_{entry.entry_id}"


@callback
def async_update_support_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    protect_version: str,
    unsupported: Iterable[OverlayCamera],
    pending: Iterable[OverlayCamera] = (),
) -> None:
    """Raise the issue for cameras that don't support the watermark.

    Only called while no camera supports it. With no unsupported cameras,
    there's nothing to explain, so the issue is cleared. Cameras that
    couldn't be checked yet are listed too, so one that never answers
    doesn't hide the others.
    """
    unsupported = list(unsupported)
    if not unsupported:
        async_delete_support_issue(hass, entry)
        return
    protect_too_old = bool(is_older(protect_version, MIN_PROTECT_VERSION))
    lines = [
        describe_camera(camera, protect_too_old=protect_too_old)
        for camera in unsupported
    ]
    lines.extend(describe_pending(camera) for camera in pending)
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id(ISSUE_NO_SUPPORTED_CAMERAS, entry),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        learn_more_url=LEARN_MORE_URL,
        translation_key=ISSUE_NO_SUPPORTED_CAMERAS,
        translation_placeholders={
            "console": escape_markdown(entry.title),
            "min_protect_version": MIN_PROTECT_VERSION,
            "min_firmware": MIN_CAMERA_FIRMWARE,
            "protect_version": describe_protect(
                protect_version, too_old=protect_too_old
            ),
            "cameras": "\n".join(f"- {line}" for line in lines),
        },
    )


@callback
def async_delete_support_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clear the issue, once a camera supports the watermark or on unload."""
    ir.async_delete_issue(hass, DOMAIN, issue_id(ISSUE_NO_SUPPORTED_CAMERAS, entry))


def escape_markdown(text: str) -> str:
    """Escape the characters that would format text in Markdown."""
    return _MARKDOWN.sub(r"\\\1", text)


def describe_protect(version: str, *, too_old: bool) -> str:
    """Describe the Protect version against the minimum."""
    version = escape_markdown(version)
    if too_old:
        return f"{version}, older than {MIN_PROTECT_VERSION}"
    return version


def _label(camera: OverlayCamera) -> str:
    name = escape_markdown(camera.name)
    if camera.model:
        return f"{name} ({escape_markdown(camera.model)})"
    return name


def describe_camera(camera: OverlayCamera, *, protect_too_old: bool = False) -> str:
    """Describe why a camera may not support the watermark.

    Protect only says a camera turned the overlay down, not why. An old
    Protect explains it for every camera, so the camera isn't judged then.
    Old firmware may be the cause, but some models never get the watermark
    whatever their firmware, so both are named.
    """
    name = _label(camera)
    firmware = escape_markdown(camera.firmware or "unknown")
    if protect_too_old:
        return f"{name}: firmware {firmware}"
    older = is_older(camera.firmware, MIN_CAMERA_FIRMWARE)
    if older:
        return (
            f"{name}: firmware {firmware} is older than {MIN_CAMERA_FIRMWARE}, "
            "or this model doesn't support it"
        )
    if older is None:
        return f"{name}: firmware {firmware}, may not support it"
    return f"{name}: firmware {firmware}, this model doesn't support it"


def describe_pending(camera: OverlayCamera) -> str:
    """Describe a camera that couldn't be checked yet."""
    return f"{_label(camera)}: couldn't be checked yet, trying again"
