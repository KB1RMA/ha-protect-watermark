"""Constants for UniFi Protect Watermark."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "protect_watermark"
PROTECT_DOMAIN: Final = "unifiprotect"

CONF_PROTECT_ENTRY_ID: Final = "protect_entry_id"

SCAN_INTERVAL: Final = timedelta(minutes=1)

# Overlay corners, as Protect names them, mapped to entity translation keys.
CORNERS: Final[dict[str, str]] = {
    "topLeft": "top_left",
    "topRight": "top_right",
    "bottomLeft": "bottom_left",
    "bottomRight": "bottom_right",
}
# Home Assistant caps text entity values at 255 characters.
HA_TEXT_MAX: Final = 255

ISSUE_PUBLIC_ONLY: Final = "protect_public_only"
ISSUE_NO_SUPPORTED_CAMERAS: Final = "no_supported_cameras"

# The first Protect release with the visible watermark, and the camera firmware
# its release notes require for it. Only used to word the repair issue: whether a
# camera gets entities depends on Protect answering its overlay request.
MIN_PROTECT_VERSION: Final = "7.2.98"
MIN_CAMERA_FIRMWARE: Final = "5.4"
