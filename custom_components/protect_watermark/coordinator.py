"""Polls the overlay settings of Protect's overlay-capable cameras."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any, cast, override

from uiprotect import ProtectApiClient
from uiprotect.exceptions import BadRequest, ClientError, NotAuthorized

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    OverlayCamera,
    ProtectPublicOnlyError,
    ProtectUnavailableError,
    adopted_cameras,
    get_overlay,
    get_protect_client,
    overlay_unsupported,
    patch_overlay,
    protect_version,
)
from .const import CONF_PROTECT_ENTRY_ID, DOMAIN, SCAN_INTERVAL
from .support import async_delete_support_issue, async_update_support_issue

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
        # Cameras that turned the overlay down for a reason other than lacking
        # it (one that's updating, for example). They're tried again on each
        # refresh, and join self.cameras once they answer.
        self.pending: dict[str, OverlayCamera] = {}
        self.unsupported: dict[str, OverlayCamera] = {}
        self._protect_version = ""
        self._discovered = False
        self._camera_listeners: list[Callable[[OverlayData], None]] = []

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
        if self.pending:
            await self._async_retry_pending(api, data)
        return data

    @callback
    def async_add_camera_listener(
        self, listener: Callable[[OverlayData], None]
    ) -> Callable[[], None]:
        """Call ``listener`` with the settings of cameras found after setup."""
        self._camera_listeners.append(listener)

        @callback
        def remove() -> None:
            self._camera_listeners.remove(listener)

        return remove

    async def _async_discover(self, api: ProtectApiClient) -> OverlayData:
        data: OverlayData = {}
        self._protect_version = protect_version(api)
        for camera in adopted_cameras(api):
            try:
                settings = await get_overlay(api, camera.id)
            except NotAuthorized as err:
                raise UpdateFailed(
                    "The UniFi Protect user can't read camera settings"
                ) from err
            except BadRequest as err:
                self._sort_rejected(api, camera, err)
                continue
            except (ClientError, TypeError) as err:
                raise UpdateFailed(
                    f"Couldn't read the overlay of {camera.name}: {err}"
                ) from err
            self.cameras[camera.id] = camera
            data[camera.id] = settings
        if self.pending:
            _LOGGER.warning(
                "Couldn't read the overlay of %s yet; trying again every %s",
                ", ".join(camera.name for camera in self.pending.values()),
                SCAN_INTERVAL,
            )
        self._discovered = True
        self._async_update_support_issue()
        return data

    async def _async_retry_pending(
        self, api: ProtectApiClient, data: OverlayData
    ) -> None:
        """Try the pending cameras again, and add the ones that answer."""
        found: OverlayData = {}
        for camera in list(self.pending.values()):
            if camera.id not in api.bootstrap.cameras:
                _LOGGER.debug("%s was removed from Protect", camera.name)
                del self.pending[camera.id]
                continue
            try:
                settings = await get_overlay(api, camera.id)
            except (ClientError, TypeError) as err:
                # A pending camera can't fail the refresh of the others.
                if isinstance(err, BadRequest) and not isinstance(err, NotAuthorized):
                    self._sort_rejected(api, camera, err)
                else:
                    _LOGGER.debug(
                        "Couldn't read the overlay of %s: %s", camera.name, err
                    )
                continue
            del self.pending[camera.id]
            self.cameras[camera.id] = camera
            data[camera.id] = found[camera.id] = settings
            _LOGGER.info("Adding the watermark of %s", camera.name)
        self._async_update_support_issue()
        if found:
            for listener in list(self._camera_listeners):
                listener(found)

    @callback
    def _sort_rejected(
        self, api: ProtectApiClient, camera: OverlayCamera, err: BadRequest
    ) -> None:
        """File a camera whose overlay read was turned down."""
        self.pending.pop(camera.id, None)
        if camera.id not in api.bootstrap.cameras:
            _LOGGER.debug("%s was removed from Protect", camera.name)
        elif overlay_unsupported(err, self._protect_version):
            # Older cameras only have the legacy OSD (name, date, logo).
            _LOGGER.debug("%s doesn't support the overlay API", camera.name)
            self.unsupported[camera.id] = camera
        else:
            _LOGGER.debug("Couldn't read the overlay of %s: %s", camera.name, err)
            self.pending[camera.id] = camera

    @callback
    def _async_update_support_issue(self) -> None:
        if self.cameras:
            async_delete_support_issue(self.hass, self.config_entry)
            return
        async_update_support_issue(
            self.hass,
            self.config_entry,
            protect_version=self._protect_version,
            unsupported=self.unsupported.values(),
            pending=self.pending.values(),
        )

    async def async_set_corner(
        self, camera_id: str, corner: str, content: str | None
    ) -> None:
        """Set one corner's text. ``None`` clears it.

        Protect stores an orientation for each corner, which its UI doesn't
        show. It's sent back unchanged so a write doesn't reset it.
        """

        def changes(settings: dict[str, Any]) -> dict[str, Any] | None:
            if corner_content(settings, corner) == (content or ""):
                return None
            if content is None:
                return {corner: None}
            value: dict[str, Any] = {"content": content}
            if (orientation := corner_orientation(settings, corner)) is not None:
                value["orientation"] = orientation
            return {corner: value}

        await self._async_patch(camera_id, changes)

    async def async_set_setting(
        self, camera_id: str, key: str, *, value: bool | float | str
    ) -> None:
        """Set one top-level overlay setting, such as ``enable``."""

        def changes(settings: dict[str, Any]) -> dict[str, Any] | None:
            if settings.get(key) == value and type(settings.get(key)) is type(value):
                return None
            return {key: value}

        await self._async_patch(camera_id, changes)

    async def _async_patch(
        self,
        camera_id: str,
        changes: Callable[[dict[str, Any]], dict[str, Any] | None],
    ) -> None:
        """Write overlay changes, skipping the write when Protect already has them.

        ``changes`` gets Protect's current settings and returns the body to
        send, or ``None`` when nothing would change.

        Protect is read first rather than trusting the last poll, so a change
        made in the Protect UI since then isn't mistaken for no change.
        """
        try:
            api = self.client()
            settings = await get_overlay(api, camera_id)
            if (body := changes(settings)) is not None:
                settings = await patch_overlay(api, camera_id, body)
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


def corner_orientation(settings: dict[str, Any], corner: str) -> str | None:
    """Return a corner's orientation, or ``None`` when the corner is empty."""
    value: object = settings.get(corner)
    if isinstance(value, dict):
        orientation: object = cast("dict[str, object]", value).get("orientation")
        if isinstance(orientation, str):
            return orientation
    return None
