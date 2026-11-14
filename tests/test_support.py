"""Tests for the repair issue raised when no camera supports the watermark."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from uiprotect.exceptions import BadRequest, NotAuthorized, NvrError

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
    make_camera,
    overlay_settings,
    setup_integration,
)

UPDATING = BadRequest("Request failed: x - Status: 409 - Reason: Camera is updating")
FRONT_DOOR_TOP_LEFT = "text.front_door_watermark_top_left"
POLL = timedelta(minutes=1, seconds=1)


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(POLL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


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


async def test_other_client_errors_skip_the_camera(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 4xx other than 400 or 404 puts that camera off, not the others."""
    fake_protect.get_error[LEGACY_CAMERA_ID] = UPDATING
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert set(config_entry.runtime_data.cameras) == {OVERLAY_CAMERA_ID}
    assert set(config_entry.runtime_data.pending) == {LEGACY_CAMERA_ID}
    assert "Couldn't read the overlay of Front Door yet; trying again" in caplog.text
    assert issue_registry.async_get_issue(DOMAIN, _issue(config_entry)) is None


async def test_pending_camera_added_later(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A pending camera gets its entities once it answers, without a reload."""
    fake_protect.get_error[LEGACY_CAMERA_ID] = UPDATING
    await setup_integration(hass, config_entry)
    assert hass.states.get(FRONT_DOOR_TOP_LEFT) is None

    del fake_protect.get_error[LEGACY_CAMERA_ID]
    fake_protect.settings[LEGACY_CAMERA_ID] = overlay_settings(
        topLeft={"content": "Front", "orientation": "horizontal"}
    )
    await _poll(hass, freezer)
    state = hass.states.get(FRONT_DOOR_TOP_LEFT)
    assert state is not None
    assert state.state == "Front"
    switch = hass.states.get("switch.front_door_watermark")
    assert switch is not None
    assert switch.state == "on"
    assert not config_entry.runtime_data.pending


async def test_pending_camera_doesnt_hold_up_the_issue(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """With no supported camera, the issue is raised and a pending one is listed.

    The pending camera keeps being tried even with no entities to poll for.
    """
    fake_protect.settings.clear()
    fake_protect.get_error[LEGACY_CAMERA_ID] = UPDATING
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    issue = issue_registry.async_get_issue(DOMAIN, _issue(config_entry))
    assert issue is not None
    assert issue.translation_placeholders is not None
    assert issue.translation_placeholders["cameras"] == (
        "- Driveway (G6 Bullet): firmware 5.4.23, this model doesn't support it\n"
        "- Front Door (G4 Doorbell): couldn't be checked yet, trying again"
    )

    # Still updating: nothing changes.
    await _poll(hass, freezer)
    assert issue_registry.async_get_issue(DOMAIN, _issue(config_entry))

    del fake_protect.get_error[LEGACY_CAMERA_ID]
    fake_protect.settings[LEGACY_CAMERA_ID] = overlay_settings()
    await _poll(hass, freezer)
    assert issue_registry.async_get_issue(DOMAIN, _issue(config_entry)) is None
    assert hass.states.get(FRONT_DOOR_TOP_LEFT) is not None


async def test_pending_camera_turns_out_unsupported(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A pending camera that answers 400 is listed as unsupported."""
    fake_protect.settings.clear()
    fake_protect.get_error[LEGACY_CAMERA_ID] = UPDATING
    await setup_integration(hass, config_entry)

    del fake_protect.get_error[LEGACY_CAMERA_ID]
    await _poll(hass, freezer)
    assert not config_entry.runtime_data.pending
    issue = issue_registry.async_get_issue(DOMAIN, _issue(config_entry))
    assert issue is not None
    assert issue.translation_placeholders is not None
    assert "couldn't be checked" not in issue.translation_placeholders["cameras"]
    assert (
        "Front Door (G4 Doorbell): firmware 4.74.106 is older"
        in (issue.translation_placeholders["cameras"])
    )


@pytest.mark.parametrize(
    "error", [NvrError("timeout"), NotAuthorized("forbidden"), UPDATING]
)
async def test_pending_camera_errors_dont_fail_the_refresh(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    error: Exception,
) -> None:
    """A pending camera that still can't be read stays pending."""
    fake_protect.get_error[LEGACY_CAMERA_ID] = UPDATING
    await setup_integration(hass, config_entry)

    fake_protect.get_error[LEGACY_CAMERA_ID] = error
    await _poll(hass, freezer)
    coordinator = config_entry.runtime_data
    assert coordinator.last_update_success
    assert set(coordinator.pending) == {LEGACY_CAMERA_ID}


async def test_pending_camera_removed(
    hass: HomeAssistant,
    protect_api: MagicMock,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A pending camera removed from Protect stops being tried."""
    fake_protect.get_error[LEGACY_CAMERA_ID] = UPDATING
    await setup_integration(hass, config_entry)

    del protect_api.bootstrap.cameras[LEGACY_CAMERA_ID]
    await _poll(hass, freezer)
    assert not config_entry.runtime_data.pending


async def test_several_pending_cameras_are_named(
    hass: HomeAssistant,
    protect_api: MagicMock,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The warning names every pending camera."""
    protect_api.bootstrap.cameras["cam3"] = make_camera("cam3", "CC", "Garage")
    fake_protect.get_error[LEGACY_CAMERA_ID] = UPDATING
    fake_protect.get_error["cam3"] = UPDATING
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert "Front Door, Garage yet" in caplog.text


async def test_removed_camera_isnt_unsupported(
    hass: HomeAssistant,
    protect_api: MagicMock,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """A camera removed from Protect during discovery isn't reported."""
    fake_protect.settings.clear()
    cameras = protect_api.bootstrap.cameras

    async def remove_and_404(url: str, method: str = "get", **kwargs: object) -> None:
        camera_id = url.split("/")[1]
        if camera_id == LEGACY_CAMERA_ID:
            del cameras[LEGACY_CAMERA_ID]
            raise BadRequest(f"Request failed: {url} - Status: 404 - Reason: Not Found")
        raise BadRequest(f"Request failed: {url} - Status: 400 - Reason: no overlay")

    protect_api.api_request.side_effect = remove_and_404
    await setup_integration(hass, config_entry)
    issue = issue_registry.async_get_issue(DOMAIN, _issue(config_entry))
    assert issue is not None
    assert issue.translation_placeholders is not None
    assert "Front Door" not in issue.translation_placeholders["cameras"]
    assert "Driveway" in issue.translation_placeholders["cameras"]


async def test_404_before_the_removal_reaches_bootstrap(
    hass: HomeAssistant,
    protect_api: MagicMock,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A 404 on a current Protect isn't read as the camera lacking the API.

    The camera may have been removed before the bootstrap heard about it, so
    it's tried again, and dropped once the bootstrap catches up.
    """
    fake_protect.settings.clear()
    fake_protect.get_error[LEGACY_CAMERA_ID] = BadRequest(
        "Request failed: x - Status: 404 - Reason: Not Found"
    )
    await setup_integration(hass, config_entry)
    assert set(config_entry.runtime_data.pending) == {LEGACY_CAMERA_ID}
    assert LEGACY_CAMERA_ID not in config_entry.runtime_data.unsupported

    del protect_api.bootstrap.cameras[LEGACY_CAMERA_ID]
    await _poll(hass, freezer)
    issue = issue_registry.async_get_issue(DOMAIN, _issue(config_entry))
    assert issue is not None
    assert issue.translation_placeholders is not None
    assert "Front Door" not in issue.translation_placeholders["cameras"]


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
    ("version", "too_old", "expected"),
    [
        ("7.2.105", False, "7.2.105"),
        ("7.1.87", True, "7.1.87, older than 7.2.98"),
        ("7.2.105_beta", False, "7.2.105\\_beta"),
    ],
)
def test_describe_protect(version: str, too_old: bool, expected: str) -> None:
    """Only a Protect version known to be too old is called out."""
    assert describe_protect(version, too_old=too_old) == expected


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
            "Porch: firmware unknown, may not support it",
        ),
        (
            OverlayCamera("1", "AA", "Porch", None, "beta-build"),
            "Porch: firmware beta-build, may not support it",
        ),
        (
            OverlayCamera("1", "AA", "*Back_Yard* #2", "G4 <Pro>", "5.4.0"),
            (
                "\\*Back\\_Yard\\* \\#2 (G4 \\<Pro\\>): firmware 5.4.0, "
                "this model doesn't support it"
            ),
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
    ("message", "version", "expected"),
    [
        ("Request failed: x - Status: 400 - Reason: no overlay", "7.2.105", True),
        # Before the watermark, Protect has no overlay route at all.
        ("Request failed: x - Status: 404 - Reason: Not Found", "7.1.87", True),
        # After it, a 404 is a camera that's gone, not one without the API.
        ("Request failed: x - Status: 404 - Reason: Not Found", "7.2.105", False),
        ("Request failed: x - Status: 404 - Reason: Not Found", "unknown", False),
        ("Request failed: x - Status: 409 - Reason: Conflict", "7.2.105", False),
        ("Request failed: x - Status: 422 - Reason: Unprocessable", "7.2.105", False),
        ("Client not initialized", "7.2.105", False),
    ],
)
def test_overlay_unsupported(message: str, version: str, expected: bool) -> None:
    """A 400, or a 404 on an old Protect, means the camera has no overlay API."""
    assert overlay_unsupported(BadRequest(message), version) is expected
