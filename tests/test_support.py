"""Tests for the repair issue raised when no camera supports the watermark."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from uiprotect.exceptions import BadRequest

from custom_components.protect_watermark.api import OverlayCamera, overlay_unsupported
from custom_components.protect_watermark.const import (
    DOMAIN,
    ISSUE_NO_SUPPORTED_CAMERAS,
)
from custom_components.protect_watermark.support import (
    describe_camera,
    describe_protect,
    issue_id,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .conftest import (
    LEGACY_CAMERA_ID,
    OVERLAY_CAMERA_ID,
    FakeProtect,
    overlay_settings,
    setup_integration,
)


def _issue(entry: MockConfigEntry) -> str:
    return issue_id(ISSUE_NO_SUPPORTED_CAMERAS, entry)


async def test_no_issue_with_a_supported_camera(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """One supported camera is enough; the unsupported one isn't reported."""
    await setup_integration(hass, config_entry)
    assert issue_registry.async_get_issue(DOMAIN, _issue(config_entry)) is None


async def test_issue_when_no_camera_supports_it(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """The issue names Protect's version and why each camera isn't supported."""
    fake_protect.settings.clear()
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    issue = issue_registry.async_get_issue(DOMAIN, _issue(config_entry))
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.translation_key == "no_supported_cameras"
    assert issue.learn_more_url is not None
    assert issue.translation_placeholders == {
        "console": "Home UDM",
        "min_protect_version": "7.2.98",
        "min_firmware": "5.4",
        "protect_version": "7.2.105",
        "cameras": (
            "- Driveway (G6 Bullet): firmware 5.4.23, this model doesn't support it\n"
            "- Front Door (G4 Doorbell): firmware 4.74.106 is older than 5.4, "
            "or this model doesn't support it"
        ),
    }

    # Once a camera supports it, a reload clears the issue.
    fake_protect.settings[OVERLAY_CAMERA_ID] = overlay_settings()
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, _issue(config_entry)) is None


async def test_no_issue_without_cameras(
    hass: HomeAssistant,
    protect_api: MagicMock,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """With no adopted cameras there's nothing to explain."""
    protect_api.bootstrap.cameras = {}
    await setup_integration(hass, config_entry)
    assert issue_registry.async_get_issue(DOMAIN, _issue(config_entry)) is None


async def test_issue_with_old_protect(
    hass: HomeAssistant,
    protect_api: MagicMock,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """An old Protect is named as the cause, and cameras aren't judged."""
    protect_api.bootstrap.nvr.version = "7.1.87"
    fake_protect.settings.clear()
    await setup_integration(hass, config_entry)

    issue = issue_registry.async_get_issue(DOMAIN, _issue(config_entry))
    assert issue is not None
    assert issue.translation_placeholders is not None
    assert issue.translation_placeholders["protect_version"] == (
        "7.1.87, older than 7.2.98"
    )
    assert issue.translation_placeholders["cameras"] == (
        "- Driveway (G6 Bullet): firmware 5.4.23\n"
        "- Front Door (G4 Doorbell): firmware 4.74.106"
    )


async def test_other_client_errors_retry(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """A 4xx other than 400 or 404 retries instead of marking a camera unsupported."""
    fake_protect.get_error[LEGACY_CAMERA_ID] = BadRequest(
        "Request failed: x - Status: 409 - Reason: Camera is updating"
    )
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert issue_registry.async_get_issue(DOMAIN, _issue(config_entry)) is None


async def test_issue_removed_on_unload(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Unloading or disabling the entry clears its issue."""
    fake_protect.settings.clear()
    await setup_integration(hass, config_entry)
    assert issue_registry.async_get_issue(DOMAIN, _issue(config_entry))

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert issue_registry.async_get_issue(DOMAIN, _issue(config_entry)) is None


async def test_issue_kept_when_unload_fails(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """The issue stays while the entry is still running."""
    fake_protect.settings.clear()
    await setup_integration(hass, config_entry)
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        assert not await hass.config_entries.async_unload(config_entry.entry_id)
    assert issue_registry.async_get_issue(DOMAIN, _issue(config_entry))


async def test_issue_removed_with_entry(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Deleting the config entry deletes its issue."""
    fake_protect.settings.clear()
    await setup_integration(hass, config_entry)
    assert issue_registry.async_get_issue(DOMAIN, _issue(config_entry))

    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, _issue(config_entry)) is None


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("7.2.105", "7.2.105"),
        ("7.2.98", "7.2.98"),
        ("7.1.87", "7.1.87, older than 7.2.98"),
        ("unknown", "unknown"),
    ],
)
def test_describe_protect(version: str, expected: str) -> None:
    """Only a Protect version known to be too old is called out."""
    assert describe_protect(version) == expected


@pytest.mark.parametrize(
    ("camera", "expected"),
    [
        (
            OverlayCamera("1", "AA", "Porch", "G6 Turret", "5.3.12"),
            (
                "Porch (G6 Turret): firmware 5.3.12 is older than 5.4, "
                "or this model doesn't support it"
            ),
        ),
        (
            OverlayCamera("1", "AA", "Porch", "G6 Turret", "5.4.0"),
            "Porch (G6 Turret): firmware 5.4.0, this model doesn't support it",
        ),
        (
            OverlayCamera("1", "AA", "Porch"),
            "Porch: firmware unknown, not supported by Protect",
        ),
        (
            OverlayCamera("1", "AA", "Porch", None, "beta-build"),
            "Porch: firmware beta-build, not supported by Protect",
        ),
    ],
)
def test_describe_camera(camera: OverlayCamera, expected: str) -> None:
    """Old firmware is named as the cause; otherwise the model is."""
    assert describe_camera(camera) == expected


def test_describe_camera_with_old_protect() -> None:
    """With Protect too old, a camera is listed without a verdict."""
    camera = OverlayCamera("1", "AA", "Porch", "G6 Turret", "5.4.0")
    assert (
        describe_camera(camera, protect_too_old=True)
        == "Porch (G6 Turret): firmware 5.4.0"
    )


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Request failed: x - Status: 400 - Reason: no overlay", True),
        ("Request failed: x - Status: 404 - Reason: Not Found", True),
        ("Request failed: x - Status: 409 - Reason: Conflict", False),
        ("Request failed: x - Status: 422 - Reason: Unprocessable", False),
        ("Client not initialized", True),
    ],
)
def test_overlay_unsupported(message: str, expected: bool) -> None:
    """Only a 400 or 404 means the camera has no overlay API."""
    assert overlay_unsupported(BadRequest(message)) is expected
