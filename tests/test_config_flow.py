"""Tests for the config flow."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.protect_watermark.const import (
    CONF_PROTECT_ENTRY_ID,
    DOMAIN,
    PROTECT_DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


async def test_aborts_without_protect(hass: HomeAssistant) -> None:
    """The flow needs a loaded UniFi Protect entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_protect"


async def test_aborts_when_protect_not_loaded(hass: HomeAssistant) -> None:
    """A UniFi Protect entry that isn't loaded doesn't count."""
    entry = MockConfigEntry(domain=PROTECT_DOMAIN, entry_id="ufp")
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_RETRY)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_protect"


async def test_single_protect_entry_is_picked(
    hass: HomeAssistant, protect_entry: MockConfigEntry
) -> None:
    """With one Protect console, the entry is created with no questions."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home UDM"
    assert result["data"] == {CONF_PROTECT_ENTRY_ID: protect_entry.entry_id}
    assert result["result"].unique_id == protect_entry.entry_id


async def test_already_configured(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Each Protect console can be set up once."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_choose_between_consoles(
    hass: HomeAssistant, protect_entry: MockConfigEntry
) -> None:
    """With more than one console, the user picks one."""
    second = MockConfigEntry(domain=PROTECT_DOMAIN, title="Cabin", entry_id="ufp2")
    second.add_to_hass(hass)
    second.mock_state(hass, ConfigEntryState.LOADED)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    # HA types async_configure's user_input as a bare dict.
    result = await hass.config_entries.flow.async_configure(  # pyright: ignore[reportUnknownMemberType]
        result["flow_id"], {CONF_PROTECT_ENTRY_ID: "ufp2"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Cabin"
    assert result["data"] == {CONF_PROTECT_ENTRY_ID: "ufp2"}


async def test_chosen_console_removed(
    hass: HomeAssistant, protect_entry: MockConfigEntry
) -> None:
    """A console removed while the form is open aborts the flow."""
    second = MockConfigEntry(domain=PROTECT_DOMAIN, title="Cabin", entry_id="ufp2")
    second.add_to_hass(hass)
    second.mock_state(hass, ConfigEntryState.LOADED)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    await hass.config_entries.async_remove("ufp2")

    # HA types async_configure's user_input as a bare dict.
    result = await hass.config_entries.flow.async_configure(  # pyright: ignore[reportUnknownMemberType]
        result["flow_id"], {CONF_PROTECT_ENTRY_ID: "ufp2"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_protect"
