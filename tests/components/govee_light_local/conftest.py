"""Tests configuration for Govee Local API."""

import asyncio
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from govee_local_api import GoveeDevice, GoveeLightCapabilities, GoveeLightFeatures
from govee_local_api.device_registry import DeviceRegistry
from govee_local_api.light_capabilities import COMMON_FEATURES, SCENE_CODES
import pytest

from homeassistant.components.govee_light_local.const import DOMAIN
from homeassistant.components.govee_light_local.coordinator import (
    GoveeController,
    GoveeLocalApiCoordinator,
)
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry


def set_mocked_devices(mock_govee_api: AsyncMock, devices: list[GoveeDevice]) -> None:
    """Update a mocked device."""
    devices_dict = {device.fingerprint: device for device in devices}
    devices_list = list(devices_dict.values())
    mock_govee_api._registry._discovered_devices = devices_dict

    type(mock_govee_api).devices = PropertyMock(return_value=devices_list)

    mock_govee_api.get_device_by_ip.side_effect = lambda ip: next(
        (device for device in mock_govee_api.devices if device.ip == ip), None
    )

    mock_govee_api.get_device_by_sku.side_effect = lambda sku: next(
        (device for device in mock_govee_api.devices if device.sku == sku), None
    )

    mock_govee_api.get_device_by_fingerprint.side_effect = lambda fingerprint: next(
        (
            device
            for device in mock_govee_api.devices
            if device.fingerprint == fingerprint
        ),
        None,
    )

    # The removal listener drops devices and the reconcile listener then reads
    # the remaining ones back, so this has to mutate the same lists rather than
    # only record the call.
    def _remove_device(device: str | GoveeDevice) -> None:
        fingerprint = device.fingerprint if isinstance(device, GoveeDevice) else device
        if removed := devices_dict.pop(fingerprint, None):
            devices_list.remove(removed)

    mock_govee_api.remove_device = MagicMock(side_effect=_remove_device)


def set_mocked_devices_side_effect(
    mock_govee_api: AsyncMock, devices: list[GoveeDevice]
) -> None:
    """Update a mocked device."""
    devices_dict = {device.fingerprint: device for device in devices}
    devices_list = list(devices_dict.values())

    type(mock_govee_api._registry)._discovered_devices = PropertyMock(
        side_effect=[[], devices_dict]
    )

    type(mock_govee_api).devices = PropertyMock(side_effect=[[], devices_list])

    mock_govee_api.get_device_by_ip.side_effect = lambda ip: next(
        (device for device in devices_list if device.ip == ip), None
    )

    mock_govee_api.get_device_by_sku.side_effect = lambda sku: next(
        (device for device in devices_list if device.sku == sku), None
    )

    mock_govee_api.get_device_by_fingerprint.side_effect = lambda fingerprint: next(
        (device for device in devices_list if device.fingerprint == fingerprint), None
    )


@pytest.fixture(name="mock_coordinator")
def fixture_mock_coordinator() -> Generator[AsyncMock]:
    """Set up Govee Local API coordinator fixture."""
    return AsyncMock(spec=GoveeLocalApiCoordinator, wraps=GoveeLocalApiCoordinator)


@pytest.fixture(name="mock_govee_api")
def fixture_mock_govee_api() -> Generator[AsyncMock]:
    """Set up Govee Local API fixture."""

    mock_registry = MagicMock(spec=DeviceRegistry, wraps=DeviceRegistry)
    mock_registry._discovered_devices = {}

    event_loop = asyncio.get_event_loop()
    controller = GoveeController(event_loop)
    controller._registry = mock_registry

    mock_api = AsyncMock(spec=GoveeController)
    mock_api._registry = mock_registry

    mock_api.start = AsyncMock()
    mock_api.cleanup = MagicMock(return_value=asyncio.Event())
    mock_api.cleanup.return_value.set()
    mock_api.turn_on_off = AsyncMock()
    mock_api.set_brightness = AsyncMock()
    mock_api.set_color = AsyncMock()
    mock_api.set_scene = AsyncMock()
    mock_api._async_update_data = AsyncMock()
    mock_api.get_device_by_ip = MagicMock()
    mock_api.get_device_by_sku = MagicMock()
    mock_api.get_device_by_fingerprint = MagicMock()
    # Mirror the controller's discovery flag so the coordinator sees a real
    # bool, the way ``GoveeController.discovery`` behaves.
    discovery_enabled = False

    def _set_discovery_enabled(enabled: bool) -> None:
        nonlocal discovery_enabled
        discovery_enabled = enabled

    mock_api.set_discovery_enabled = MagicMock(side_effect=_set_discovery_enabled)
    type(mock_api).discovery = PropertyMock(side_effect=lambda: discovery_enabled)

    # The reconcile listener reads and mutates the queue, so back it with a
    # real set rather than a bare mock attribute.
    discovery_queue: set[str] = set()

    def _add_to_queue(ip: str) -> bool:
        discovery_queue.add(ip)
        return True

    mock_api.add_device_to_discovery_queue = MagicMock(side_effect=_add_to_queue)
    mock_api.remove_device_from_discovery_queue = MagicMock(
        side_effect=discovery_queue.discard
    )
    type(mock_api).discovery_queue = PropertyMock(side_effect=lambda: discovery_queue)

    type(mock_api).devices = PropertyMock(return_value=[])

    with (
        patch(
            "homeassistant.components.govee_light_local.coordinator.GoveeController",
            return_value=mock_api,
        ) as mock_controller,
        patch(
            "homeassistant.components.govee_light_local.config_flow.GoveeController",
            return_value=mock_api,
        ),
    ):
        yield mock_controller.return_value


@pytest.fixture(name="mock_setup_entry")
def fixture_mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "homeassistant.components.govee_light_local.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        yield mock_setup_entry


DEFAULT_CAPABILITIES: GoveeLightCapabilities = GoveeLightCapabilities(
    features=COMMON_FEATURES, segments=[], scenes={}
)

SCENE_CAPABILITIES: GoveeLightCapabilities = GoveeLightCapabilities(
    features=COMMON_FEATURES | GoveeLightFeatures.SCENES,
    segments=[],
    scenes=SCENE_CODES,
)


async def setup_light(
    hass: HomeAssistant,
    mock_govee_api: AsyncMock,
    capabilities: GoveeLightCapabilities = DEFAULT_CAPABILITIES,
    *,
    ip: str = "192.168.1.100",
    fingerprint: str = "asdawdqwdqwd",
    sku: str = "H615A",
) -> tuple[MockConfigEntry, GoveeDevice]:
    """Set up a single mocked Govee light device and return its entry and device.

    The returned tuple lets tests that need to mutate the device after setup
    (e.g. ``device.update(...)`` in availability tests) access the underlying
    ``GoveeDevice`` directly. Tests that only need the entry or neither can
    discard the unused half with ``_``.
    """
    device = GoveeDevice(
        controller=mock_govee_api,
        ip=ip,
        fingerprint=fingerprint,
        sku=sku,
        capabilities=capabilities,
    )
    set_mocked_devices(mock_govee_api, [device])

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    return entry, device
