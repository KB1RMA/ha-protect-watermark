"""Text entities for the corners of each camera's watermark."""

from __future__ import annotations

import logging
from typing import Any, cast, override

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import OverlayCamera
from .const import CORNERS, DEFAULT_ENABLED_CORNER, HA_TEXT_MAX
from .coordinator import OverlayCoordinator, ProtectWatermarkConfigEntry, corner_content

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProtectWatermarkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one text entity per watermark corner of each overlay-capable camera."""
    coordinator = entry.runtime_data
    device_registry = dr.async_get(hass)
    entities: list[WatermarkCornerText] = []
    for camera in coordinator.cameras.values():
        # The entities join the camera's device, which the UniFi Protect
        # integration owns. A device belongs to one config entry, so they link
        # to it with ``device_entry`` rather than registering device info.
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
        settings = coordinator.data.get(camera.id) or {}
        anchors = capability(settings, "anchors", list(CORNERS))
        entities.extend(
            WatermarkCornerText(coordinator, camera, device, corner, settings)
            for corner in CORNERS
            if corner in anchors
        )
    async_add_entities(entities)


class WatermarkCornerText(CoordinatorEntity[OverlayCoordinator], TextEntity):
    """The text in one corner of a camera's watermark.

    Placeholders such as ``{Datetime}`` and ``{CameraName}`` are passed through
    to Protect. An empty value clears the corner.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = TextMode.TEXT
    _attr_native_min = 0

    def __init__(
        self,
        coordinator: OverlayCoordinator,
        camera: OverlayCamera,
        device: dr.DeviceEntry,
        corner: str,
        settings: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._camera = camera
        self._corner = corner
        self._attr_translation_key = f"watermark_{CORNERS[corner]}"
        self._attr_unique_id = f"{camera.mac}_watermark_{CORNERS[corner]}"
        self._attr_entity_registry_enabled_default = corner == DEFAULT_ENABLED_CORNER
        self.device_entry = device
        max_length = capability(settings, "maxContentLength", HA_TEXT_MAX)
        self._attr_native_max = min(max_length, HA_TEXT_MAX)
        self._update_from_data()

    @property
    @override
    def available(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Available while this camera's overlay could be read."""
        return super().available and self._settings is not None

    @property
    def _settings(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get(self._camera.id)

    @callback
    def _update_from_data(self) -> None:
        settings = self._settings
        self._attr_native_value = (
            corner_content(settings, self._corner) if settings is not None else None
        )

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        self._update_from_data()
        super()._handle_coordinator_update()

    @override
    async def async_set_value(self, value: str) -> None:
        """Set the corner's text. An empty value clears the corner."""
        await self.coordinator.async_set_corner(
            self._camera.id, self._corner, value or None
        )


def capability[T](settings: dict[str, Any], name: str, default: T) -> T:
    """Return a camera capability, or the default when it's missing or the wrong type."""
    capabilities: object = settings.get("capabilities")
    if isinstance(capabilities, dict):
        value: object = cast("dict[str, object]", capabilities).get(name)
        if isinstance(value, type(default)) and not isinstance(value, bool):
            return value
    return default
