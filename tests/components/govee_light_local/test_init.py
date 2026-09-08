"""Test Govee light local setup and teardown."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.govee_light_local.const import CLEANUP_TIMEOUT, DOMAIN
from homeassistant.components.network import Adapter
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .conftest import setup_light

from tests.common import MockConfigEntry

DISABLED_ADAPTERS: list[Adapter] = [
    {
        "name": "eth0",
        "index": 1,
        "enabled": False,
        "auto": False,
        "default": False,
        "ipv4": [{"address": "192.168.1.2", "network_prefix": 24}],
        "ipv6": [],
    },
]


@pytest.mark.usefixtures("mock_network_adapters")
async def test_unload_releases_port(
    hass: HomeAssistant, mock_govee_api: AsyncMock
) -> None:
    """Test unloading waits for the controller to release the listening port."""

    entry, _ = await setup_light(hass, mock_govee_api)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    mock_govee_api.cleanup.assert_called_once_with(timeout=CLEANUP_TIMEOUT)


@pytest.mark.usefixtures("mock_network_adapters", "mock_stuck_cleanup")
async def test_unload_warns_when_port_not_released(
    hass: HomeAssistant, mock_govee_api: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    """Test a controller that never closes its sockets does not wedge the unload."""

    entry, _ = await setup_light(hass, mock_govee_api)

    with patch(
        "homeassistant.components.govee_light_local.coordinator.CLEANUP_WAIT_TIMEOUT", 0
    ):
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert "Timed out waiting for port 4002 to be released" in caplog.text


async def test_no_enabled_adapters(
    hass: HomeAssistant, mock_govee_api: AsyncMock
) -> None:
    """Test setup is retried when there is no enabled address to listen on."""

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.network.async_get_adapters",
        return_value=DISABLED_ADAPTERS,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    mock_govee_api.start.assert_not_called()
