"""A sensor for how much of the picture each camera's watermark covers."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import OverlayCamera
from .coordinator import OverlayCoordinator, ProtectWatermarkConfigEntry
from .entity import WatermarkEntity, async_add_camera_entities

PARALLEL_UPDATES = 0

AREA = "overlayAreaPercent"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProtectWatermarkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a watermark area sensor for each overlay camera."""
    coordinator = entry.runtime_data
    async_add_camera_entities(
        hass,
        entry,
        async_add_entities,
        lambda camera, device, _: [WatermarkAreaSensor(coordinator, camera, device)],
    )


class WatermarkAreaSensor(WatermarkEntity, SensorEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Protect's ``overlayAreaPercent``: the share of the picture the watermark covers.

    Protect works this out from the text and ignores writes to it. The camera's
    limit is its ``maxAreaPercent`` capability.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: OverlayCoordinator,
        camera: OverlayCamera,
        device: dr.DeviceEntry,
    ) -> None:
        super().__init__(coordinator, camera, device, "watermark_area")

    @callback
    @override
    def _update_from_settings(self, settings: dict[str, Any]) -> None:
        value = settings.get(AREA)
        self._attr_native_value = (
            value
            if isinstance(value, int | float) and not isinstance(value, bool)
            else None
        )
