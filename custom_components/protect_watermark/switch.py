"""A switch that turns each camera's whole watermark on or off."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import OverlayCamera
from .coordinator import OverlayCoordinator, ProtectWatermarkConfigEntry
from .entity import WatermarkEntity, camera_devices

PARALLEL_UPDATES = 1

ENABLE = "enable"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProtectWatermarkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a watermark switch for each overlay camera."""
    coordinator = entry.runtime_data
    async_add_entities(
        WatermarkSwitch(coordinator, camera, device)
        for camera, device, _ in camera_devices(hass, coordinator)
    )


class WatermarkSwitch(WatermarkEntity, SwitchEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Whether the camera shows its watermark at all."""

    def __init__(
        self,
        coordinator: OverlayCoordinator,
        camera: OverlayCamera,
        device: dr.DeviceEntry,
    ) -> None:
        super().__init__(coordinator, camera, device, "watermark")

    @callback
    @override
    def _update_from_settings(self, settings: dict[str, Any]) -> None:
        value = settings.get(ENABLE)
        self._attr_is_on = value if isinstance(value, bool) else None

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Show the watermark."""
        await self.coordinator.async_set_setting(self._camera.id, ENABLE, value=True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Hide the watermark."""
        await self.coordinator.async_set_setting(self._camera.id, ENABLE, value=False)
