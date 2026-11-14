"""Tests for diagnostics."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.protect_watermark.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.core import HomeAssistant

from .conftest import OVERLAY_CAMERA_ID, overlay_settings, setup_integration


async def test_diagnostics(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Diagnostics hold each overlay camera's settings as Protect sent them."""
    await setup_integration(hass, config_entry)

    result = await async_get_config_entry_diagnostics(hass, config_entry)

    assert result == {
        "cameras": {
            "Driveway": {
                "id": OVERLAY_CAMERA_ID,
                "overlay_settings": overlay_settings(),
            }
        }
    }
