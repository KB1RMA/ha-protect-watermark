"""Text entities for each camera's watermark corners and date format."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import OverlayCamera
from .const import CORNERS, HA_TEXT_MAX
from .coordinator import OverlayCoordinator, ProtectWatermarkConfigEntry, corner_content
from .entity import WatermarkEntity, anchors, camera_devices, capability

PARALLEL_UPDATES = 1

DATETIME_FORMAT = "datetimeFormat"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProtectWatermarkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the corner and date format text entities of each overlay camera."""
    coordinator = entry.runtime_data
    entities: list[TextEntity] = []
    for camera, device, settings in camera_devices(hass, coordinator):
        entities.extend(
            WatermarkCornerText(coordinator, camera, device, corner, settings)
            for corner in anchors(settings)
        )
        entities.append(WatermarkDatetimeFormatText(coordinator, camera, device))
    async_add_entities(entities)


class WatermarkCornerText(WatermarkEntity, TextEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """The text in one corner of a camera's watermark.

    Placeholders such as ``{Datetime}`` and ``{CameraName}`` are passed through
    to Protect. An empty value clears the corner.
    """

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
        self._corner = corner
        max_length = capability(settings, "maxContentLength", HA_TEXT_MAX)
        self._attr_native_max = min(max_length, HA_TEXT_MAX)
        super().__init__(coordinator, camera, device, f"watermark_{CORNERS[corner]}")

    @callback
    @override
    def _update_from_settings(self, settings: dict[str, Any]) -> None:
        self._attr_native_value = corner_content(settings, self._corner)

    @override
    async def async_set_value(self, value: str) -> None:
        """Set the corner's text. An empty value clears the corner."""
        await self.coordinator.async_set_corner(
            self._camera.id, self._corner, value or None
        )


class WatermarkDatetimeFormatText(WatermarkEntity, TextEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """The strftime format of the ``{Datetime}`` placeholder."""

    _attr_mode = TextMode.TEXT
    _attr_native_min = 1
    _attr_native_max = HA_TEXT_MAX
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: OverlayCoordinator,
        camera: OverlayCamera,
        device: dr.DeviceEntry,
    ) -> None:
        super().__init__(coordinator, camera, device, "watermark_datetime_format")

    @callback
    @override
    def _update_from_settings(self, settings: dict[str, Any]) -> None:
        value = settings.get(DATETIME_FORMAT)
        self._attr_native_value = value if isinstance(value, str) else None

    @override
    async def async_set_value(self, value: str) -> None:
        """Set the date format, such as ``%Y-%m-%d %r``."""
        await self.coordinator.async_set_setting(
            self._camera.id, DATETIME_FORMAT, value=value
        )
