"""Tests for the watermark text entities."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from uiprotect.exceptions import NotAuthorized, NvrError

from homeassistant.components.text.const import (
    ATTR_MAX,
    ATTR_VALUE,
    DOMAIN as TEXT_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import (
    DATETIME_FORMAT,
    OVERLAY_CAMERA_ID,
    OVERLAY_CAMERA_MAC,
    TOP_LEFT,
    TOP_RIGHT,
    FakeProtect,
    add_protect_device,
    overlay_settings,
    setup_integration,
)

POLL = timedelta(minutes=1, seconds=1)


async def set_value(hass: HomeAssistant, entity_id: str, value: str) -> None:
    """Call text.set_value."""
    await hass.services.async_call(
        TEXT_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )


def corner_entries(
    entity_registry: er.EntityRegistry, config_entry: MockConfigEntry
) -> list[er.RegistryEntry]:
    """Return the corner text entities of the config entry."""
    return [
        entry
        for entry in er.async_entries_for_config_entry(
            entity_registry, config_entry.entry_id
        )
        if entry.domain == "text" and "datetime" not in entry.unique_id
    ]


async def test_entities(
    hass: HomeAssistant,
    protect_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Overlay-capable cameras get four corner entities on their existing device."""
    await setup_integration(hass, config_entry)

    entries = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    texts = [entry for entry in entries if entry.domain == "text"]
    assert sorted(entry.unique_id for entry in texts) == [
        f"{OVERLAY_CAMERA_MAC}_watermark_bottom_left",
        f"{OVERLAY_CAMERA_MAC}_watermark_bottom_right",
        f"{OVERLAY_CAMERA_MAC}_watermark_datetime_format",
        f"{OVERLAY_CAMERA_MAC}_watermark_top_left",
        f"{OVERLAY_CAMERA_MAC}_watermark_top_right",
    ]
    # All four corners are enabled by default; the date format isn't.
    disabled = [entry.entity_id for entry in texts if entry.disabled_by is not None]
    assert disabled == [DATETIME_FORMAT]

    device = device_registry.async_get_device_by_connection(
        (dr.CONNECTION_NETWORK_MAC, dr.format_mac(OVERLAY_CAMERA_MAC)),
        protect_entry.entry_id,
    )
    assert device is not None
    assert device.name == "Driveway"
    assert all(entry.device_id == device.id for entry in entries)
    # The entities join the Protect device; this integration creates none.
    assert (
        dr.async_entries_for_config_entry(device_registry, config_entry.entry_id) == []
    )
    assert device.config_entry_id == protect_entry.entry_id

    state = hass.states.get(TOP_RIGHT)
    assert state is not None
    assert state.state == ""
    assert state.attributes[ATTR_MAX] == 255


async def test_top_left_reads_existing_text(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A corner shows Protect's text."""
    await setup_integration(hass, config_entry)

    state = hass.states.get(TOP_LEFT)
    assert state is not None
    assert state.state == "{Datetime} {CameraName}"


async def test_set_value_changes_only_its_corner(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """Setting a value sends only that corner, saved, not as a preview."""
    await setup_integration(hass, config_entry)
    await set_value(hass, TOP_RIGHT, "41°F")

    assert fake_protect.patches == [
        (OVERLAY_CAMERA_ID, {"topRight": {"content": "41°F"}, "preview": False})
    ]
    state = hass.states.get(TOP_RIGHT)
    assert state is not None
    assert state.state == "41°F"
    topleft = fake_protect.settings[OVERLAY_CAMERA_ID]["topLeft"]
    assert topleft["content"] == "{Datetime} {CameraName}"


async def test_same_value_is_not_sent(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """An unchanged value makes no request to Protect."""
    fake_protect.settings[OVERLAY_CAMERA_ID] = overlay_settings(
        topRight={"content": "41°F", "orientation": "horizontal"}
    )
    await setup_integration(hass, config_entry)
    await set_value(hass, TOP_RIGHT, "41°F")
    assert fake_protect.patches == []


async def test_value_matching_stale_data_is_sent(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """Protect is read before skipping, so a change made since the poll isn't missed."""
    fake_protect.settings[OVERLAY_CAMERA_ID] = overlay_settings(
        topRight={"content": "41°F", "orientation": "horizontal"}
    )
    await setup_integration(hass, config_entry)
    # Moved to another corner in the Protect UI since the last poll.
    fake_protect.settings[OVERLAY_CAMERA_ID] = overlay_settings(
        bottomRight={"content": "41°F", "orientation": "horizontal"}
    )
    await set_value(hass, TOP_RIGHT, "41°F")

    assert fake_protect.patches == [
        (
            OVERLAY_CAMERA_ID,
            {"topRight": {"content": "41°F"}, "preview": False},
        )
    ]
    state = hass.states.get("text.driveway_watermark_bottom_right")
    assert state is not None
    assert state.state == "41°F"


async def test_set_value_keeps_orientation(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """Changing a corner's text keeps its orientation."""
    fake_protect.settings[OVERLAY_CAMERA_ID] = overlay_settings(
        topRight={"content": "41°F", "orientation": "vertical"}
    )
    await setup_integration(hass, config_entry)
    await set_value(hass, TOP_RIGHT, "42°F")
    assert fake_protect.patches == [
        (
            OVERLAY_CAMERA_ID,
            {
                "topRight": {"content": "42°F", "orientation": "vertical"},
                "preview": False,
            },
        )
    ]


async def test_read_error_before_write(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """A failed read before a write is raised and nothing is sent."""
    await setup_integration(hass, config_entry)
    fake_protect.get_error[OVERLAY_CAMERA_ID] = NvrError("offline")
    with pytest.raises(HomeAssistantError, match="Couldn't set the watermark"):
        await set_value(hass, TOP_RIGHT, "41°F")
    assert fake_protect.patches == []


async def test_datetime_format(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """The date format reads and writes Protect's datetimeFormat."""
    await setup_integration(hass, config_entry)
    entity_registry.async_update_entity(DATETIME_FORMAT, disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(DATETIME_FORMAT)
    assert state is not None
    assert state.state == "%Y-%m-%d  %r"

    await set_value(hass, DATETIME_FORMAT, "%H:%M")
    assert fake_protect.patches == [
        (OVERLAY_CAMERA_ID, {"datetimeFormat": "%H:%M", "preview": False})
    ]
    state = hass.states.get(DATETIME_FORMAT)
    assert state is not None
    assert state.state == "%H:%M"

    fake_protect.settings[OVERLAY_CAMERA_ID]["datetimeFormat"] = None
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(DATETIME_FORMAT)
    assert state is not None
    assert state.state == "unknown"


async def test_empty_value_clears_corner(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """An empty value clears the corner in Protect."""
    fake_protect.settings[OVERLAY_CAMERA_ID] = overlay_settings(
        topRight={"content": "41°F", "orientation": "horizontal"}
    )
    await setup_integration(hass, config_entry)
    await set_value(hass, TOP_RIGHT, "")

    assert fake_protect.patches == [
        (OVERLAY_CAMERA_ID, {"topRight": None, "preview": False})
    ]
    state = hass.states.get(TOP_RIGHT)
    assert state is not None
    assert state.state == ""


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (NotAuthorized("403"), "isn't allowed to change camera settings"),
        (NvrError("timeout"), "Couldn't set the watermark on Driveway"),
    ],
)
async def test_set_value_errors(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    error: Exception,
    message: str,
) -> None:
    """Protect errors are raised to the caller and the state is unchanged."""
    await setup_integration(hass, config_entry)
    fake_protect.patch_error = error
    with pytest.raises(HomeAssistantError, match=message):
        await set_value(hass, TOP_RIGHT, "41°F")
    assert len(fake_protect.patches) == 1
    state = hass.states.get(TOP_RIGHT)
    assert state is not None
    assert state.state == ""


async def test_set_value_unexpected_response(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """A response without settings is an error."""
    await setup_integration(hass, config_entry)
    fake_protect.patch_response = {"warnings": []}
    with pytest.raises(HomeAssistantError, match="Couldn't set the watermark"):
        await set_value(hass, TOP_RIGHT, "41°F")


async def test_set_value_protect_unloaded(
    hass: HomeAssistant,
    protect_entry: MockConfigEntry,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
) -> None:
    """With UniFi Protect unloaded, setting a value fails without a request."""
    await setup_integration(hass, config_entry)
    protect_entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
    with pytest.raises(HomeAssistantError, match="isn't available"):
        await set_value(hass, TOP_RIGHT, "41°F")
    assert fake_protect.patches == []


async def test_poll_picks_up_changes(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Changes made in the Protect UI show up on the next poll."""
    await setup_integration(hass, config_entry)
    fake_protect.settings[OVERLAY_CAMERA_ID] = overlay_settings(
        topRight={"content": "set in Protect", "orientation": "horizontal"}
    )
    freezer.tick(POLL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(TOP_RIGHT)
    assert state is not None
    assert state.state == "set in Protect"


async def test_poll_camera_error_makes_it_unavailable(
    hass: HomeAssistant,
    protect_entry: MockConfigEntry,
    fake_protect: FakeProtect,
    protect_api: MagicMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A camera that can't be read goes unavailable, then recovers."""
    second = "cam-second"
    fake_protect.settings[second] = overlay_settings()
    protect_api.bootstrap.cameras[second] = MagicMock(
        id=second, mac="F09FC2000003", is_adopted_by_us=True
    )
    protect_api.bootstrap.cameras[second].name = None
    add_protect_device(hass, protect_entry, "F09FC2000003", "Garage")
    await setup_integration(hass, config_entry)
    second_entity = "text.garage_watermark_top_right"
    state = hass.states.get(second_entity)
    assert state is not None

    fake_protect.get_error[OVERLAY_CAMERA_ID] = NvrError("offline")
    freezer.tick(POLL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(TOP_RIGHT)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE
    state = hass.states.get(second_entity)
    assert state is not None
    assert state.state == ""

    del fake_protect.get_error[OVERLAY_CAMERA_ID]
    freezer.tick(POLL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(TOP_RIGHT)
    assert state is not None
    assert state.state == ""


@pytest.mark.parametrize(
    "error", [NvrError("offline"), NotAuthorized("403")], ids=["error", "auth"]
)
async def test_poll_failure_makes_all_unavailable(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    error: Exception,
) -> None:
    """When no camera can be read, every entity goes unavailable."""
    await setup_integration(hass, config_entry)
    fake_protect.get_error[OVERLAY_CAMERA_ID] = error
    freezer.tick(POLL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(TOP_RIGHT)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


@pytest.mark.parametrize("public_only", [False, True], ids=["unloaded", "public"])
async def test_poll_without_protect(
    hass: HomeAssistant,
    protect_entry: MockConfigEntry,
    protect_api: MagicMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    public_only: bool,
) -> None:
    """Entities go unavailable while UniFi Protect can't be used."""
    await setup_integration(hass, config_entry)
    if public_only:
        protect_api.is_public_only = True
    else:
        protect_entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
    freezer.tick(POLL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(TOP_RIGHT)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


async def test_missing_capabilities(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Without reported capabilities, all corners and the default limit are used."""
    settings = overlay_settings()
    settings["capabilities"] = None
    fake_protect.settings[OVERLAY_CAMERA_ID] = settings
    await setup_integration(hass, config_entry)
    assert len(corner_entries(entity_registry, config_entry)) == 4
    state = hass.states.get(TOP_RIGHT)
    assert state is not None
    assert state.attributes[ATTR_MAX] == 255


async def test_small_capabilities(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """A camera's own limits are respected."""
    settings = overlay_settings()
    settings["capabilities"]["anchors"] = ["topLeft", "topRight"]
    settings["capabilities"]["maxContentLength"] = 32
    fake_protect.settings[OVERLAY_CAMERA_ID] = settings
    await setup_integration(hass, config_entry)
    assert len(corner_entries(entity_registry, config_entry)) == 2
    state = hass.states.get(TOP_RIGHT)
    assert state is not None
    assert state.attributes[ATTR_MAX] == 32


@pytest.mark.parametrize("bad", [True, "4096"], ids=["bool", "string"])
async def test_wrong_type_capability(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    bad: object,
) -> None:
    """A capability of the wrong type falls back to the default."""
    settings = overlay_settings()
    settings["capabilities"]["maxContentLength"] = bad
    fake_protect.settings[OVERLAY_CAMERA_ID] = settings
    await setup_integration(hass, config_entry)
    state = hass.states.get(TOP_RIGHT)
    assert state is not None
    assert state.attributes[ATTR_MAX] == 255


async def test_corner_without_text(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """A corner object without text reads as empty."""
    fake_protect.settings[OVERLAY_CAMERA_ID] = overlay_settings(
        topRight={"orientation": "horizontal"}
    )
    await setup_integration(hass, config_entry)
    state = hass.states.get(TOP_RIGHT)
    assert state is not None
    assert state.state == ""


async def test_camera_without_device_is_skipped(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    protect_api: MagicMock,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A camera with no Protect device in Home Assistant gets no entities."""
    orphan = "cam-orphan"
    fake_protect.settings[orphan] = overlay_settings()
    protect_api.bootstrap.cameras[orphan] = MagicMock(
        id=orphan, mac="F09FC2000004", is_adopted_by_us=True
    )
    protect_api.bootstrap.cameras[orphan].name = "Shed"
    await setup_integration(hass, config_entry)
    assert len(corner_entries(entity_registry, config_entry)) == 4
    assert "Skipping Shed" in caplog.text


async def test_set_value_corner_without_orientation(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """A corner Protect stored without an orientation is sent without one."""
    fake_protect.settings[OVERLAY_CAMERA_ID] = overlay_settings(
        topRight={"content": "41°F"}
    )
    await setup_integration(hass, config_entry)
    await set_value(hass, TOP_RIGHT, "42°F")
    assert fake_protect.patches == [
        (OVERLAY_CAMERA_ID, {"topRight": {"content": "42°F"}, "preview": False})
    ]
