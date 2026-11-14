"""Constants for UniFi Protect Watermark."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "protect_watermark"
PROTECT_DOMAIN: Final = "unifiprotect"

CONF_PROTECT_ENTRY_ID: Final = "protect_entry_id"

SCAN_INTERVAL: Final = timedelta(minutes=5)

# Overlay corners, as Protect names them, mapped to entity translation keys.
CORNERS: Final[dict[str, str]] = {
    "topLeft": "top_left",
    "topRight": "top_right",
    "bottomLeft": "bottom_left",
    "bottomRight": "bottom_right",
}
# Only this corner's entity is enabled by default. On a camera with the default
# watermark, top-left holds "{Datetime} {CameraName}" and the rest are empty.
DEFAULT_ENABLED_CORNER: Final = "topRight"

# Home Assistant caps text entity values at 255 characters.
HA_TEXT_MAX: Final = 255

ISSUE_PUBLIC_ONLY: Final = "protect_public_only"
