"""Fixtures for UniFi Protect Watermark tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from uiprotect import ProtectApiClient
from uiprotect.exceptions import BadRequest

from custom_components.protect_watermark.const import (
    CONF_PROTECT_ENTRY_ID,
    DOMAIN,
    PROTECT_DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

OVERLAY_CAMERA_ID = "cam-overlay"
OVERLAY_CAMERA_MAC = "F09FC2000010"
LEGACY_CAMERA_ID = "cam-legacy"
LEGACY_CAMERA_MAC = "F09FC2000001"
OTHER_NVR_CAMERA_ID = "cam-other-nvr"

TOP_RIGHT = "text.driveway_watermark_top_right"
TOP_LEFT = "text.driveway_watermark_top_left"
DATETIME_FORMAT = "text.driveway_watermark_date_format"
WATERMARK_SWITCH = "switch.driveway_watermark"
AREA = "sensor.driveway_watermark_area"


def overlay_settings(**corners: dict[str, str] | None) -> dict[str, Any]:
    """Return overlay settings shaped like Protect 7.2's GET response."""
    settings: dict[str, Any] = {
        "deviceId": "0",
        "enable": True,
        "testMode": False,
        "cameraName": "Driveway",
        "datetimeFormat": "%Y-%m-%d  %r",
        "topLeft": {"content": "{Datetime} {CameraName}", "orientation": "horizontal"},
        "topRight": None,
        "bottomLeft": None,
        "bottomRight": None,
        "customLogoFileId": None,
        "source": "overlay",
        "overlayAreaPercent": 2,
        "capabilities": {
            "placeholders": ["{Datetime}", "{CameraName}"],
            "anchors": ["topLeft", "topRight", "bottomLeft", "bottomRight"],
            "maxAreaPercent": 20,
            "maxSegmentsPerCorner": 8,
            "maxContentLength": 4096,
            "maxContentLines": 32,
        },
    }
    settings.update(corners)
    return settings


@dataclass
class FakeProtect:
    """A stand-in for Protect's private overlay API."""

    settings: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {OVERLAY_CAMERA_ID: overlay_settings()}
    )
    patches: list[tuple[str, dict[str, Any]]] = field(
        default_factory=list[tuple[str, dict[str, Any]]]
    )
    get_error: dict[str, Exception] = field(default_factory=dict[str, Exception])
    patch_error: Exception | None = None
    patch_response: Any = None

    async def api_request(
        self, url: str, method: str = "get", **kwargs: Any
    ) -> dict[str, Any] | list[Any] | None:
        """Answer the overlay routes the integration uses."""
        parts = url.split("/")
        assert parts[0] == "cameras"
        assert parts[2] == "overlay-settings"
        camera_id = parts[1]
        if method == "get":
            if camera_id in self.get_error:
                raise self.get_error[camera_id]
            if camera_id not in self.settings:
                raise BadRequest("Camera does not support the overlay API")
            return deepcopy(self.settings[camera_id])
        assert method == "patch"
        body: dict[str, Any] = kwargs["json"]
        self.patches.append((camera_id, body))
        if self.patch_error is not None:
            raise self.patch_error
        if self.patch_response is not None:
            return self.patch_response
        changes = {key: value for key, value in body.items() if key != "preview"}
        self.settings[camera_id] = {**self.settings[camera_id], **changes}
        return {
            "settings": deepcopy(self.settings[camera_id]),
            "warnings": [],
            "areaBudgetExceeded": False,
            "preview": False,
            "previewExpiresAt": None,
        }


def _camera(camera_id: str, mac: str, name: str, *, ours: bool = True) -> MagicMock:
    camera = MagicMock()
    camera.id = camera_id
    camera.mac = mac
    camera.name = name
    camera.is_adopted_by_us = ours
    return camera


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Load the integration from custom_components."""


@pytest.fixture
def fake_protect() -> FakeProtect:
    """Return the fake Protect overlay API."""
    return FakeProtect()


@pytest.fixture
def protect_api(fake_protect: FakeProtect) -> MagicMock:
    """Return a client like the UniFi Protect integration's."""
    api = MagicMock(spec=ProtectApiClient)
    api.is_public_only = False
    api.api_request = AsyncMock(side_effect=fake_protect.api_request)
    api.bootstrap.cameras = {
        OVERLAY_CAMERA_ID: _camera(OVERLAY_CAMERA_ID, OVERLAY_CAMERA_MAC, "Driveway"),
        LEGACY_CAMERA_ID: _camera(LEGACY_CAMERA_ID, LEGACY_CAMERA_MAC, "Front Door"),
        OTHER_NVR_CAMERA_ID: _camera(
            OTHER_NVR_CAMERA_ID, "F09FC2000002", "Not ours", ours=False
        ),
    }
    return api


@pytest.fixture
def protect_entry(hass: HomeAssistant, protect_api: MagicMock) -> MockConfigEntry:
    """Return a loaded UniFi Protect config entry with its camera devices."""
    entry = MockConfigEntry(domain=PROTECT_DOMAIN, title="Home UDM", entry_id="ufp")
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    # Stands in for the integration's ProtectData. async_stop is called when
    # the entry unloads at the end of a test.
    entry.runtime_data = SimpleNamespace(api=protect_api, async_stop=AsyncMock())
    for mac, name in (
        (OVERLAY_CAMERA_MAC, "Driveway"),
        (LEGACY_CAMERA_MAC, "Front Door"),
    ):
        add_protect_device(hass, entry, mac, name)
    return entry


def add_protect_device(
    hass: HomeAssistant, entry: MockConfigEntry, mac: str, name: str
) -> dr.DeviceEntry:
    """Register a camera device the way the UniFi Protect integration does."""
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        name=name,
    )


@pytest.fixture
def config_entry(
    hass: HomeAssistant, protect_entry: MockConfigEntry
) -> MockConfigEntry:
    """Return this integration's config entry, added but not set up."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=protect_entry.title,
        unique_id=protect_entry.entry_id,
        data={CONF_PROTECT_ENTRY_ID: protect_entry.entry_id},
    )
    entry.add_to_hass(hass)
    return entry


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry and wait for it."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
