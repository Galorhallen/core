"""Test Govee light local sensor platform."""

from unittest.mock import AsyncMock, MagicMock

from govee_local_api import GoveeDevice

from homeassistant.components.govee_light_local.const import DOMAIN
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import DEFAULT_CAPABILITIES, set_mocked_devices

from tests.common import MockConfigEntry


async def test_sensor_known_device(
    hass: HomeAssistant, mock_govee_api: AsyncMock
) -> None:
    """Test sensor entity is created for a known device."""
    set_mocked_devices(
        mock_govee_api,
        [
            GoveeDevice(
                controller=mock_govee_api,
                ip="192.168.1.100",
                fingerprint="asdawdqwdqwd",
                sku="H615A",
                capabilities=DEFAULT_CAPABILITIES,
            )
        ],
    )

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Entity is registered but disabled by default
    ent_reg = er.async_get(hass)
    entity_entry = ent_reg.async_get("sensor.h615a_ip_address")
    assert entity_entry is not None
    assert entity_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    # Enable the entity and reload
    ent_reg.async_update_entity("sensor.h615a_ip_address", disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    sensor = hass.states.get("sensor.h615a_ip_address")
    assert sensor is not None
    assert sensor.state == "192.168.1.100"


async def test_sensor_diagnostic_category(
    hass: HomeAssistant, mock_govee_api: AsyncMock
) -> None:
    """Test sensor has diagnostic entity category."""
    set_mocked_devices(
        mock_govee_api,
        [
            GoveeDevice(
                controller=mock_govee_api,
                ip="192.168.1.100",
                fingerprint="asdawdqwdqwd",
                sku="H615A",
                capabilities=DEFAULT_CAPABILITIES,
            )
        ],
    )

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    ent_reg = er.async_get(hass)
    entity_entry = ent_reg.async_get("sensor.h615a_ip_address")
    assert entity_entry is not None
    assert entity_entry.entity_category is EntityCategory.DIAGNOSTIC
    assert entity_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_sensor_discovered_device(
    hass: HomeAssistant, mock_govee_api: AsyncMock
) -> None:
    """Test sensor is created for newly discovered devices."""
    set_mocked_devices(mock_govee_api, [])

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"auto_discovery": False},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # No sensors initially
    ent_reg = er.async_get(hass)
    assert ent_reg.async_get("sensor.h615a_ip_address") is None

    # Simulate device discovery
    new_device = GoveeDevice(
        controller=mock_govee_api,
        ip="192.168.1.200",
        fingerprint="new_device_fp",
        sku="H615A",
        capabilities=DEFAULT_CAPABILITIES,
    )

    # Trigger the discovery callback
    coordinator = entry.runtime_data
    for callback in coordinator.new_device_callbacks:
        callback(new_device)
    await hass.async_block_till_done()

    # Entities are registered but disabled by default
    entity_entry = ent_reg.async_get("sensor.h615a_ip_address")
    assert entity_entry is not None
    assert entity_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    interface_entry = ent_reg.async_get("sensor.h615a_listening_interface")
    assert interface_entry is not None
    assert interface_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_listening_interface_sensor_with_transport(
    hass: HomeAssistant, mock_govee_api: AsyncMock
) -> None:
    """Test listening interface sensor returns the correct address."""
    device = GoveeDevice(
        controller=mock_govee_api,
        ip="192.168.1.100",
        fingerprint="asdawdqwdqwd",
        sku="H615A",
        capabilities=DEFAULT_CAPABILITIES,
    )

    mock_transport = MagicMock()
    device._transport = mock_transport

    mock_protocol = MagicMock()
    mock_protocol.transport = mock_transport
    mock_protocol.listening_address = "192.168.1.1"
    mock_govee_api.protocols = [mock_protocol]

    set_mocked_devices(mock_govee_api, [device])

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Enable the entity and reload
    ent_reg = er.async_get(hass)
    ent_reg.async_update_entity("sensor.h615a_listening_interface", disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    sensor = hass.states.get("sensor.h615a_listening_interface")
    assert sensor is not None
    assert sensor.state == "192.168.1.1"


async def test_listening_interface_sensor_no_transport(
    hass: HomeAssistant, mock_govee_api: AsyncMock
) -> None:
    """Test listening interface sensor returns unknown when no transport."""
    device = GoveeDevice(
        controller=mock_govee_api,
        ip="192.168.1.100",
        fingerprint="asdawdqwdqwd",
        sku="H615A",
        capabilities=DEFAULT_CAPABILITIES,
    )

    mock_govee_api.protocols = []

    set_mocked_devices(mock_govee_api, [device])

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Enable the entity and reload
    ent_reg = er.async_get(hass)
    ent_reg.async_update_entity("sensor.h615a_listening_interface", disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    sensor = hass.states.get("sensor.h615a_listening_interface")
    assert sensor is not None
    assert sensor.state == "unknown"


async def test_listening_interface_sensor_diagnostic_category(
    hass: HomeAssistant, mock_govee_api: AsyncMock
) -> None:
    """Test listening interface sensor has diagnostic entity category."""
    mock_govee_api.protocols = []

    set_mocked_devices(
        mock_govee_api,
        [
            GoveeDevice(
                controller=mock_govee_api,
                ip="192.168.1.100",
                fingerprint="asdawdqwdqwd",
                sku="H615A",
                capabilities=DEFAULT_CAPABILITIES,
            )
        ],
    )

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    ent_reg = er.async_get(hass)
    entity_entry = ent_reg.async_get("sensor.h615a_listening_interface")
    assert entity_entry is not None
    assert entity_entry.entity_category is EntityCategory.DIAGNOSTIC
    assert entity_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
