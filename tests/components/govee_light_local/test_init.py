"""Tests init for the Govee Local API integration."""

from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
from govee_local_api import GoveeDevice
import pytest

from homeassistant import config_entries
from homeassistant.components.govee_light_local import async_remove_config_entry_device
from homeassistant.components.govee_light_local.const import (
    CONF_AUTO_DISCOVERY,
    CONF_MANUAL_DEVICES,
    DEVICE_TIMEOUT,
    DOMAIN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from .conftest import DEFAULT_CAPABILITIES, set_mocked_devices

from tests.common import MockConfigEntry
from tests.typing import WebSocketGenerator


async def test_setup_entry_with_options(
    hass: HomeAssistant, mock_govee_api: AsyncMock
) -> None:
    """Test update options triggers reload."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_AUTO_DISCOVERY: False,
            CONF_MANUAL_DEVICES: ["192.168.1.100"],
        },
    )

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    mock_govee_api.add_device_to_discovery_queue.assert_called_once_with(
        "192.168.1.100"
    )


@pytest.mark.parametrize(
    ("auto_discovery", "expected_state"),
    [
        (False, config_entries.ConfigEntryState.LOADED),
        (True, config_entries.ConfigEntryState.SETUP_RETRY),
    ],
    ids=["disabled_loads_empty", "enabled_waits_for_devices"],
)
async def test_setup_discovery_wait_follows_options(
    hass: HomeAssistant,
    mock_govee_api: AsyncMock,
    auto_discovery: bool,
    expected_state: config_entries.ConfigEntryState,
) -> None:
    """Test the setup discovery wait honors the auto-discovery option.

    With auto-discovery off the controller never probes, so waiting for a
    device would strand the entry in a permanent retry loop. The setting lives
    in options, so setup must read it from there.
    """
    set_mocked_devices(mock_govee_api, [])

    config_entry = MockConfigEntry(
        domain=DOMAIN, options={CONF_AUTO_DISCOVERY: auto_discovery}
    )
    config_entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.govee_light_local.DISCOVERY_TIMEOUT",
        0,
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is expected_state


async def test_update_options_remove_device_discovered(
    hass: HomeAssistant,
    mock_govee_api: AsyncMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a discovered manual device is removed when dropped from options."""

    manual_device1 = GoveeDevice(
        controller=mock_govee_api,
        ip="192.168.1.100",
        fingerprint="manual_device1-fingerprint",
        sku="H615A",
        capabilities=DEFAULT_CAPABILITIES,
    )
    manual_device1.is_manual = True
    manual_device2 = GoveeDevice(
        controller=mock_govee_api,
        ip="192.168.1.101",
        fingerprint="manual_device2-fingerprint",
        sku="H615B",
        capabilities=DEFAULT_CAPABILITIES,
    )
    manual_device2.is_manual = True
    set_mocked_devices(mock_govee_api, [manual_device1, manual_device2])

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_AUTO_DISCOVERY: False,
            CONF_MANUAL_DEVICES: [manual_device1.ip, manual_device2.ip],
        },
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is config_entries.ConfigEntryState.LOADED
    assert entity_registry.async_get("light.h615a") is not None
    assert entity_registry.async_get("light.h615b") is not None

    # Dropping the IP from the desired set is the whole removal instruction.
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            CONF_AUTO_DISCOVERY: False,
            CONF_MANUAL_DEVICES: [manual_device2.ip],
        },
    )
    set_mocked_devices(mock_govee_api, [manual_device2])
    await hass.async_block_till_done()

    assert config_entry.state is config_entries.ConfigEntryState.LOADED
    mock_govee_api.remove_device_from_discovery_queue.assert_called_once_with(
        manual_device1.ip
    )
    assert entity_registry.async_get("light.h615b") is not None
    assert entity_registry.async_get("light.h615a") is None


async def test_update_options_remove_multiple_devices(
    hass: HomeAssistant,
    mock_govee_api: AsyncMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test removing several devices in a single options update.

    The remove form allows multiple selections, so the listener has to cope
    with more than one device disappearing at once.
    """

    devices = []
    for index, (ip, sku) in enumerate(
        [("192.168.1.100", "H615A"), ("192.168.1.101", "H615B")]
    ):
        device = GoveeDevice(
            controller=mock_govee_api,
            ip=ip,
            fingerprint=f"manual_device{index}-fingerprint",
            sku=sku,
            capabilities=DEFAULT_CAPABILITIES,
        )
        device.is_manual = True
        devices.append(device)
    set_mocked_devices(mock_govee_api, devices)

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_AUTO_DISCOVERY: False,
            CONF_MANUAL_DEVICES: [device.ip for device in devices],
        },
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert entity_registry.async_get("light.h615a") is not None
    assert entity_registry.async_get("light.h615b") is not None

    hass.config_entries.async_update_entry(
        config_entry,
        options={CONF_AUTO_DISCOVERY: False, CONF_MANUAL_DEVICES: []},
    )
    set_mocked_devices(mock_govee_api, [])
    await hass.async_block_till_done()

    assert config_entry.state is config_entries.ConfigEntryState.LOADED
    assert mock_govee_api.remove_device_from_discovery_queue.call_count == 2
    # The options are the source of truth; the listener must not rewrite them.
    assert config_entry.options == {
        CONF_AUTO_DISCOVERY: False,
        CONF_MANUAL_DEVICES: [],
    }
    assert entity_registry.async_get("light.h615a") is None
    assert entity_registry.async_get("light.h615b") is None


async def test_update_options_remove_device_in_queue(
    hass: HomeAssistant, mock_govee_api: AsyncMock
) -> None:
    """Test removing a manual device that was never discovered."""

    manual_device1 = GoveeDevice(
        controller=mock_govee_api,
        ip="192.168.1.100",
        fingerprint="manual_device1-fingerprint",
        sku="H615A",
        capabilities=DEFAULT_CAPABILITIES,
    )
    manual_device1.is_manual = True
    set_mocked_devices(mock_govee_api, [manual_device1])

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_AUTO_DISCOVERY: False,
            CONF_MANUAL_DEVICES: [manual_device1.ip],
        },
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Queue an IP that never answers, then drop it again.
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            CONF_AUTO_DISCOVERY: False,
            CONF_MANUAL_DEVICES: [manual_device1.ip, "192.168.1.101"],
        },
    )
    await hass.async_block_till_done()
    assert "192.168.1.101" in mock_govee_api.discovery_queue

    hass.config_entries.async_update_entry(
        config_entry,
        options={
            CONF_AUTO_DISCOVERY: False,
            CONF_MANUAL_DEVICES: [manual_device1.ip],
        },
    )
    await hass.async_block_till_done()

    assert config_entry.state is config_entries.ConfigEntryState.LOADED
    assert "192.168.1.101" not in mock_govee_api.discovery_queue
    # The already-discovered device is untouched.
    assert len(hass.states.async_all()) == 1


async def test_update_options_enable_discovery(
    hass: HomeAssistant, mock_govee_api: AsyncMock
) -> None:
    """Test update options triggers reload."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        options={CONF_AUTO_DISCOVERY: False},
    )

    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert config_entry.state is config_entries.ConfigEntryState.LOADED

    hass.config_entries.async_update_entry(
        config_entry,
        options={CONF_AUTO_DISCOVERY: True},
    )
    await hass.async_block_till_done()

    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert config_entry.state is config_entries.ConfigEntryState.LOADED
    mock_govee_api.set_discovery_enabled.assert_called_once_with(True)


async def test_update_options_add_devices(
    hass: HomeAssistant, mock_govee_api: AsyncMock
) -> None:
    """Test adding multiple devices via options."""

    device1 = GoveeDevice(
        controller=mock_govee_api,
        ip="192.168.1.100",
        fingerprint="device1-fingerprint",
        sku="H615A",
        capabilities=DEFAULT_CAPABILITIES,
    )
    device1.is_manual = True

    device2 = GoveeDevice(
        controller=mock_govee_api,
        ip="192.168.1.101",
        fingerprint="device2-fingerprint",
        sku="H6199",
        capabilities=DEFAULT_CAPABILITIES,
    )
    device2.is_manual = True

    set_mocked_devices(mock_govee_api, [])

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        options={CONF_AUTO_DISCOVERY: False},
    )

    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    set_mocked_devices(mock_govee_api, [device1])
    mock_govee_api.get_device_by_ip.side_effect = [None, device1]

    hass.config_entries.async_update_entry(
        config_entry,
        options={
            CONF_AUTO_DISCOVERY: False,
            CONF_MANUAL_DEVICES: [device1.ip],
        },
    )

    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    mock_govee_api.add_device_to_discovery_queue.assert_called_once_with(device1.ip)


async def test_setup_without_source_ips(
    hass: HomeAssistant, mock_govee_api: AsyncMock
) -> None:
    """Test setup is retried when no IPv4 interface is enabled."""
    config_entry = MockConfigEntry(domain=DOMAIN)
    config_entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.network.async_get_enabled_source_ips",
        return_value=[],
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is config_entries.ConfigEntryState.SETUP_RETRY


async def test_remove_config_entry_device(
    hass: HomeAssistant,
    mock_govee_api: AsyncMock,
    device_registry: dr.DeviceRegistry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test only devices that stopped answering may be deleted."""
    device = GoveeDevice(
        controller=mock_govee_api,
        ip="192.168.1.100",
        fingerprint="asdawdqwdqwd",
        sku="H615A",
        capabilities=DEFAULT_CAPABILITIES,
    )
    # A second device makes sure the lookup skips unrelated ones.
    other = GoveeDevice(
        controller=mock_govee_api,
        ip="192.168.1.101",
        fingerprint="other-fingerprint",
        sku="H615B",
        capabilities=DEFAULT_CAPABILITIES,
    )
    set_mocked_devices(mock_govee_api, [other, device])

    config_entry = MockConfigEntry(domain=DOMAIN)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, device.fingerprint), config_entry.entry_id
    )
    assert device_entry is not None

    # Still answering, so it would only be rediscovered. The user gets a
    # specific reason rather than the generic core rejection message.
    with pytest.raises(HomeAssistantError) as err:
        await async_remove_config_entry_device(hass, config_entry, device_entry)
    assert err.value.translation_key == "device_still_online"
    assert err.value.translation_domain == DOMAIN

    # Once it has been silent past the timeout the user may clean it up. The
    # controller never evicts devices, so this is the only signal available.
    freezer.tick(DEVICE_TIMEOUT * 2)
    assert await async_remove_config_entry_device(hass, config_entry, device_entry)


async def test_remove_device_websocket_error_is_meaningful(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    mock_govee_api: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test the delete button surfaces a useful reason, not a generic one.

    Returning False from the removal hook yields core's opaque "rejected by
    integration" text, so the integration raises a translated error instead.
    """
    assert await async_setup_component(hass, "config", {})

    device = GoveeDevice(
        controller=mock_govee_api,
        ip="192.168.1.100",
        fingerprint="asdawdqwdqwd",
        sku="H615A",
        capabilities=DEFAULT_CAPABILITIES,
    )
    set_mocked_devices(mock_govee_api, [device])

    config_entry = MockConfigEntry(domain=DOMAIN)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, device.fingerprint), config_entry.entry_id
    )
    assert device_entry is not None

    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "config/device_registry/remove",
            "device_id": device_entry.id,
        }
    )
    response = await client.receive_json()

    assert not response["success"]
    error = response["error"]
    assert error["translation_domain"] == DOMAIN
    assert error["translation_key"] == "device_still_online"
    # The message itself is already localized, so a client that only reads
    # `message` still shows something useful.
    assert "still responding on your network" in error["message"]
    assert "rejected by integration" not in error["message"]
