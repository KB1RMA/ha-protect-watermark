"""Diagnostics for UniFi Protect Watermark."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import ProtectWatermarkConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ProtectWatermarkConfigEntry
) -> dict[str, Any]:
    """Return each overlay-capable camera's overlay settings as Protect sent them."""
    coordinator = entry.runtime_data
    return {
        "cameras": {
            camera.name: {
                "id": camera.id,
                "overlay_settings": (coordinator.data or {}).get(camera.id),
            }
            for camera in coordinator.cameras.values()
        },
    }
