"""Tests for the watermark switch."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.switch.const import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant

from .conftest import (
    OVERLAY_CAMERA_ID,
    WATERMARK_SWITCH,
    FakeProtect,
    overlay_settings,
    setup_integration,
)


async def call(hass: HomeAssistant, service: str) -> None:
    """Call a switch service on the watermark switch."""
    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: WATERMARK_SWITCH}, blocking=True
    )


async def test_turn_off_and_on(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """The switch sets Protect's enable flag, and skips a write that changes nothing."""
    await setup_integration(hass, config_entry)
    state = hass.states.get(WATERMARK_SWITCH)
    assert state is not None
    assert state.state == STATE_ON

    await call(hass, SERVICE_TURN_ON)
    assert fake_protect.patches == []

    await call(hass, SERVICE_TURN_OFF)
    assert fake_protect.patches == [
        (OVERLAY_CAMERA_ID, {"enable": False, "preview": False})
    ]
    state = hass.states.get(WATERMARK_SWITCH)
    assert state is not None
    assert state.state == STATE_OFF

    await call(hass, SERVICE_TURN_ON)
    assert fake_protect.patches[-1] == (
        OVERLAY_CAMERA_ID,
        {"enable": True, "preview": False},
    )
    state = hass.states.get(WATERMARK_SWITCH)
    assert state is not None
    assert state.state == STATE_ON


async def test_missing_enable(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """Without an enable flag, the switch is unknown."""
    settings = overlay_settings()
    del settings["enable"]
    fake_protect.settings[OVERLAY_CAMERA_ID] = settings
    await setup_integration(hass, config_entry)
    state = hass.states.get(WATERMARK_SWITCH)
    assert state is not None
    assert state.state == STATE_UNKNOWN
