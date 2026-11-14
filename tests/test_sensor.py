"""Tests for the watermark area sensor."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import AREA, OVERLAY_CAMERA_ID, FakeProtect, setup_integration


@pytest.mark.parametrize(
    ("value", "expected"), [(2, "2"), (None, STATE_UNKNOWN), (True, STATE_UNKNOWN)]
)
async def test_area(
    hass: HomeAssistant,
    fake_protect: FakeProtect,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    value: object,
    expected: str,
) -> None:
    """The sensor shows Protect's overlayAreaPercent, and is disabled by default."""
    fake_protect.settings[OVERLAY_CAMERA_ID]["overlayAreaPercent"] = value
    await setup_integration(hass, config_entry)
    entry = entity_registry.async_get(AREA)
    assert entry is not None
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    entity_registry.async_update_entity(AREA, disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(AREA)
    assert state is not None
    assert state.state == expected
