"""UniFi Protect Watermark: set the text of Protect's camera watermark from Home Assistant."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir

from .api import ProtectPublicOnlyError, ProtectUnavailableError, get_protect_client
from .const import (
    CONF_PROTECT_ENTRY_ID,
    DOMAIN,
    ISSUE_NO_SUPPORTED_CAMERAS,
    ISSUE_PUBLIC_ONLY,
)
from .coordinator import OverlayCoordinator, ProtectWatermarkConfigEntry
from .support import issue_id

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ProtectWatermarkConfigEntry
) -> bool:
    """Set up UniFi Protect Watermark from a config entry."""
    protect_entry_id: str = entry.data[CONF_PROTECT_ENTRY_ID]
    public_only_issue = issue_id(ISSUE_PUBLIC_ONLY, entry)
    try:
        get_protect_client(hass, protect_entry_id)
    except ProtectPublicOnlyError as err:
        ir.async_create_issue(
            hass,
            DOMAIN,
            public_only_issue,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_PUBLIC_ONLY,
        )
        raise ConfigEntryError(
            "The UniFi Protect integration has no private API access"
        ) from err
    except ProtectUnavailableError as err:
        raise ConfigEntryNotReady("The UniFi Protect integration isn't loaded") from err
    ir.async_delete_issue(hass, DOMAIN, public_only_issue)

    coordinator = OverlayCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ProtectWatermarkConfigEntry
) -> bool:
    """Unload a config entry.

    Its cameras are checked again on the next setup, so the support issue
    doesn't outlive a disabled or unloaded entry.
    """
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    ir.async_delete_issue(hass, DOMAIN, issue_id(ISSUE_NO_SUPPORTED_CAMERAS, entry))
    return True


async def async_remove_entry(
    hass: HomeAssistant, entry: ProtectWatermarkConfigEntry
) -> None:
    """Remove the repair issues when the entry is deleted."""
    for key in (ISSUE_PUBLIC_ONLY, ISSUE_NO_SUPPORTED_CAMERAS):
        ir.async_delete_issue(hass, DOMAIN, issue_id(key, entry))
