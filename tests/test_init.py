"""Tests for setting up and unloading the integration."""

from __future__ import annotations

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry
from uiprotect.exceptions import NotAuthorized, NvrError

from custom_components.protect_watermark.const import DOMAIN, ISSUE_PUBLIC_ONLY
from custom_components.protect_watermark.support import issue_id
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .conftest import OVERLAY_CAMERA_ID, FakeProtect, setup_integration


async def test_setup_and_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """The entry loads and unloads."""
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_retries_while_protect_not_loaded(
    hass: HomeAssistant,
    protect_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
) -> None:
    """Setup waits for the UniFi Protect integration."""
    protect_entry.mock_state(hass, ConfigEntryState.SETUP_RETRY)
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_retries_when_protect_has_no_client(
    hass: HomeAssistant,
    protect_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
) -> None:
    """A Protect entry whose runtime data has no client isn't usable."""
    protect_entry.runtime_data = object()
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_public_only_raises_repair(
    hass: HomeAssistant,
    protect_api: MagicMock,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Without private API access, setup fails with a repair issue."""
    protect_api.is_public_only = True
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    public_only_issue = issue_id(ISSUE_PUBLIC_ONLY, config_entry)
    assert issue_registry.async_get_issue(DOMAIN, public_only_issue) is not None

    # Once private access is back, a reload clears the issue.
    protect_api.is_public_only = False
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert issue_registry.async_get_issue(DOMAIN, public_only_issue) is None


async def test_remove_clears_repair(
    hass: HomeAssistant,
    protect_api: MagicMock,
    config_entry: MockConfigEntry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Deleting the entry deletes its repair issue."""
    protect_api.is_public_only = True
    await setup_integration(hass, config_entry)
    await hass.config_entries.async_remove(config_entry.entry_id)
    public_only_issue = issue_id(ISSUE_PUBLIC_ONLY, config_entry)
    assert issue_registry.async_get_issue(DOMAIN, public_only_issue) is None


async def test_discovery_not_authorized(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """A Protect user that can't read settings makes setup retry."""
    fake_protect.get_error[OVERLAY_CAMERA_ID] = NotAuthorized("403")
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_discovery_error(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """An error reading a camera during discovery makes setup retry."""
    fake_protect.get_error[OVERLAY_CAMERA_ID] = NvrError("timeout")
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_discovery_unexpected_response(
    hass: HomeAssistant, fake_protect: FakeProtect, config_entry: MockConfigEntry
) -> None:
    """A response that isn't an object makes setup retry."""
    fake_protect.settings[OVERLAY_CAMERA_ID] = []  # pyright: ignore[reportArgumentType]
    await setup_integration(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
