"""Polls the overlay settings of Protect's overlay-capable cameras."""

from __future__ import annotations

import logging
from typing import Any, cast, override

from uiprotect import ProtectApiClient
from uiprotect.exceptions import BadRequest, ClientError, NotAuthorized

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    OverlayCamera,
    ProtectPublicOnlyError,
    ProtectUnavailableError,
    adopted_cameras,
    get_overlay,
    get_protect_client,
    set_corner,
)
from .const import CONF_PROTECT_ENTRY_ID, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type ProtectWatermarkConfigEntry = ConfigEntry[OverlayCoordinator]

# Camera id -> overlay settings, or None when the last read of that camera failed.
type OverlayData = dict[str, dict[str, Any] | None]


class OverlayCoordinator(DataUpdateCoordinator[OverlayData]):
    """Reads the overlay settings of every overlay-capable camera."""

    config_entry: ProtectWatermarkConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ProtectWatermarkConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.protect_entry_id: str = entry.data[CONF_PROTECT_ENTRY_ID]
        # Found on the first refresh. Cameras added to Protect later appear
        # after this integration is reloaded.
        self.cameras: dict[str, OverlayCamera] = {}
        self._discovered = False

    def client(self) -> ProtectApiClient:
        """Return the UniFi Protect integration's client."""
        return get_protect_client(self.hass, self.protect_entry_id)

    @override
    async def _async_update_data(self) -> OverlayData:
        try:
            api = self.client()
        except ProtectPublicOnlyError as err:
            raise UpdateFailed(
                "The UniFi Protect integration has no private API access"
            ) from err
        except ProtectUnavailableError as err:
            raise UpdateFailed("The UniFi Protect integration isn't loaded") from err

        if not self._discovered:
            return await self._async_discover(api)

        data: OverlayData = {}
        failures = 0
        for camera_id in self.cameras:
            try:
                data[camera_id] = await get_overlay(api, camera_id)
            except NotAuthorized as err:
                raise UpdateFailed(
                    "The UniFi Protect user can't read camera settings"
                ) from err
            except (ClientError, TypeError) as err:
                _LOGGER.debug("Couldn't read the overlay of %s: %s", camera_id, err)
                data[camera_id] = None
                failures += 1
        if self.cameras and failures == len(self.cameras):
            raise UpdateFailed("Couldn't read the overlay of any camera")
        return data

    async def _async_discover(self, api: ProtectApiClient) -> OverlayData:
        data: OverlayData = {}
        for camera in adopted_cameras(api):
            try:
                settings = await get_overlay(api, camera.id)
            except NotAuthorized as err:
                raise UpdateFailed(
                    "The UniFi Protect user can't read camera settings"
                ) from err
            except BadRequest:
                # Older cameras only have the legacy OSD (name, date, logo).
                _LOGGER.debug("%s doesn't support the overlay API", camera.name)
                continue
            except (ClientError, TypeError) as err:
                raise UpdateFailed(
                    f"Couldn't read the overlay of {camera.name}: {err}"
                ) from err
            self.cameras[camera.id] = camera
            data[camera.id] = settings
        self._discovered = True
        return data

    async def async_set_corner(
        self, camera_id: str, corner: str, content: str | None
    ) -> None:
        """Set one corner of a camera's overlay, skipping writes that change nothing."""
        current = (self.data or {}).get(camera_id)
        if current is not None and corner_content(current, corner) == (content or ""):
            return
        try:
            api = self.client()
            settings = await set_corner(api, camera_id, corner, content)
        except (ProtectUnavailableError, ProtectPublicOnlyError) as err:
            raise HomeAssistantError(
                "The UniFi Protect integration isn't available"
            ) from err
        except NotAuthorized as err:
            raise HomeAssistantError(
                "The UniFi Protect user isn't allowed to change camera settings"
            ) from err
        except (ClientError, TypeError) as err:
            raise HomeAssistantError(
                f"Couldn't set the watermark on {self.cameras[camera_id].name}: {err}"
            ) from err
        self.async_set_updated_data({**(self.data or {}), camera_id: settings})


def corner_content(settings: dict[str, Any], corner: str) -> str:
    """Return a corner's text, or an empty string when the corner is empty."""
    value: object = settings.get(corner)
    if isinstance(value, dict):
        content: object = cast("dict[str, object]", value).get("content")
        if isinstance(content, str):
            return content
    return ""
