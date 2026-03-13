"""Coordinator for Govee light local."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Self

from govee_local_api import GoveeController, GoveeDevice

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_AUTO_DISCOVERY,
    CONF_DISCOVERY_INTERVAL_DEFAULT,
    CONF_IPS_TO_REMOVE,
    CONF_LISTENING_INTERFACES,
    CONF_LISTENING_PORT_DEFAULT,
    CONF_MANUAL_DEVICES,
    CONF_MULTICAST_ADDRESS_DEFAULT,
    CONF_OPTION_MODE,
    CONF_TARGET_PORT_DEFAULT,
    SCAN_INTERVAL,
    OptionMode,
)

_LOGGER = logging.getLogger(__name__)

type GoveeLocalConfigEntry = ConfigEntry[GoveeLocalApiCoordinator]


@dataclass
class GoveeLocalApiConfig:
    """Govee light local configuration."""

    auto_discovery: bool
    manual_devices: set[str]
    ips_to_remove: set[str]
    option_mode: OptionMode | None
    listening_interfaces: list[str]

    @classmethod
    def from_config_entry(cls, config_entry: GoveeLocalConfigEntry) -> Self:
        """Return Govee light local configuration from config entry."""

        config = config_entry.data
        options = config_entry.options

        option_mode: str | None = options.get(CONF_OPTION_MODE, None)

        return cls(
            options.get(CONF_AUTO_DISCOVERY, config.get(CONF_AUTO_DISCOVERY, True)),
            set(options.get(CONF_MANUAL_DEVICES, [])),
            set(options.get(CONF_IPS_TO_REMOVE, [])),
            OptionMode(option_mode) if option_mode else None,
            list(
                options.get(
                    CONF_LISTENING_INTERFACES,
                    config.get(CONF_LISTENING_INTERFACES, []),
                )
            ),
        )


class GoveeLocalApiCoordinator(DataUpdateCoordinator[list[GoveeDevice]]):
    """Govee light local coordinator."""

    config_entry: GoveeLocalConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: GoveeLocalConfigEntry,
        source_ips: set[str],
    ) -> None:
        """Initialize my coordinator."""
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            config_entry=config_entry,
            name="GoveeLightLocalApi",
            update_interval=SCAN_INTERVAL,
        )

        self.new_device_callbacks: list[Callable[[GoveeDevice], None]] = []

        config: GoveeLocalApiConfig = GoveeLocalApiConfig.from_config_entry(
            config_entry
        )

        self._controller = GoveeController(
            loop=hass.loop,
            logger=_LOGGER,
            listening_addresses=list(source_ips),
            broadcast_address=CONF_MULTICAST_ADDRESS_DEFAULT,
            broadcast_port=CONF_TARGET_PORT_DEFAULT,
            listening_port=CONF_LISTENING_PORT_DEFAULT,
            discovery_enabled=config.auto_discovery,
            discovery_interval=CONF_DISCOVERY_INTERVAL_DEFAULT,
            update_enabled=False,
        )

    def _on_device_discovered(self, device: GoveeDevice, is_new: bool) -> bool:
        """Handle device discovery and fan out to registered platform callbacks."""
        if is_new:
            for callback in self.new_device_callbacks:
                callback(device)
        return True

    async def start(self) -> None:
        """Start the Govee coordinator."""
        self._controller.set_device_discovered_callback(self._on_device_discovered)
        await self._controller.start()
        self._controller.send_update_message()

    def enable_discovery(self, enable: bool) -> None:
        """Enable or disable automatic Govee light discovery."""
        self._controller.set_discovery_enabled(enable)

    def add_device_to_discovery_queue(self, ip: str) -> bool:
        """Add a device by IP address to discovery queue."""
        return self._controller.add_device_to_discovery_queue(ip)

    def remove_device_from_discovery_queue(self, ip: str) -> None:
        """Remove a device by IP address from manual discovery queue."""
        self._controller.remove_device_from_discovery_queue(ip)

    def remove_device(self, device: GoveeDevice) -> None:
        """Remove a device from the controller."""
        self._controller.remove_device(device)

    def get_device_by_ip(self, ip: str) -> GoveeDevice | None:
        """Return a device by IP address."""
        return self._controller.get_device_by_ip(ip)

    def cleanup(self) -> asyncio.Event:
        """Stop and cleanup the coordinator."""
        return self._controller.cleanup()

    async def turn_on(self, device: GoveeDevice) -> None:
        """Turn on the light."""
        await device.turn_on()

    async def turn_off(self, device: GoveeDevice) -> None:
        """Turn off the light."""
        await device.turn_off()

    async def set_brightness(self, device: GoveeDevice, brightness: int) -> None:
        """Set light brightness."""
        await device.set_brightness(brightness)

    async def set_rgb_color(
        self, device: GoveeDevice, red: int, green: int, blue: int
    ) -> None:
        """Set light RGB color."""
        await device.set_rgb_color(red, green, blue)

    async def set_temperature(self, device: GoveeDevice, temperature: int) -> None:
        """Set light color in kelvin."""
        await device.set_temperature(temperature)

    async def set_scene(self, device: GoveeDevice, scene: str) -> None:
        """Set light scene."""
        await device.set_scene(scene)

    def get_device_listening_address(self, device: GoveeDevice) -> str | None:
        """Return the listening address for the interface a device communicates through."""
        device_transport = device.transport
        if device_transport is None:
            return None
        for protocol in self._controller.protocols:
            if protocol.transport == device_transport:
                return protocol.listening_address
        return None

    @property
    def devices(self) -> list[GoveeDevice]:
        """Return a list of discovered Govee devices."""
        return self._controller.devices

    @property
    def discovery_queue(self) -> set[str]:
        """Return a set of devices in the discovery queue."""
        return self._controller.discovery_queue

    @property
    def discovery_enabled(self) -> bool:
        """Return if discovery is enabled."""
        return self._controller.discovery

    async def _async_update_data(self) -> list[GoveeDevice]:
        self._controller.send_update_message()
        return self._controller.devices
