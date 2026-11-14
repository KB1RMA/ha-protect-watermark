"""Base entity for the watermark settings of a Protect camera."""

from __future__ import annotations

from collections.abc import Iterator
import logging
from typing import Any, cast, override

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import OverlayCamera
from .const import CORNERS
from .coordinator import OverlayCoordinator

_LOGGER = logging.getLogger(__name__)


def camera_devices(
    hass: HomeAssistant, coordinator: OverlayCoordinator
) -> Iterator[tuple[OverlayCamera, dr.DeviceEntry, dict[str, Any]]]:
    """Yield each overlay camera with its UniFi Protect device and settings.

    Entities join the camera's device, which the UniFi Protect integration
    owns. A device belongs to one config entry, so they link to it with
    ``device_entry`` rather than registering device info.
    """
    device_registry = dr.async_get(hass)
    for camera in coordinator.cameras.values():
        device = device_registry.async_get_device_by_connection(
            (dr.CONNECTION_NETWORK_MAC, dr.format_mac(camera.mac)),
            coordinator.protect_entry_id,
        )
        if device is None:
            _LOGGER.warning(
                "Skipping %s: the UniFi Protect integration has no device for it",
                camera.name,
            )
            continue
        yield camera, device, coordinator.data.get(camera.id) or {}


def capability[T](settings: dict[str, Any], name: str, default: T) -> T:
    """Return a camera capability, or the default when it's missing or the wrong type."""
    capabilities: object = settings.get("capabilities")
    if isinstance(capabilities, dict):
        value: object = cast("dict[str, object]", capabilities).get(name)
        if isinstance(value, type(default)) and not isinstance(value, bool):
            return value
    return default


def anchors(settings: dict[str, Any]) -> list[str]:
    """Return the corners this camera supports, in Protect's names."""
    supported = capability(settings, "anchors", list(CORNERS))
    return [corner for corner in CORNERS if corner in supported]


class WatermarkEntity(CoordinatorEntity[OverlayCoordinator]):
    """A watermark setting of one camera, on its UniFi Protect device."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: OverlayCoordinator,
        camera: OverlayCamera,
        device: dr.DeviceEntry,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._camera = camera
        self._attr_translation_key = key
        self._attr_unique_id = f"{camera.mac}_{key}"
        self.device_entry = device
        self._update_from_data()

    @property
    @override
    def available(self) -> bool:
        """Available while this camera's overlay could be read."""
        return super().available and self._settings is not None

    @property
    def _settings(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get(self._camera.id)

    @callback
    def _update_from_data(self) -> None:
        """Copy the coordinator's data into the entity's attributes."""
        if (settings := self._settings) is not None:
            self._update_from_settings(settings)

    @callback
    def _update_from_settings(self, settings: dict[str, Any]) -> None:
        """Copy a camera's overlay settings into the entity's attributes."""
        raise NotImplementedError  # pragma: no cover

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        self._update_from_data()
        super()._handle_coordinator_update()
