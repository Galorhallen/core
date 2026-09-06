"""Coordinator for Govee light local."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Self, override

from govee_local_api import GoveeController, GoveeDevice

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_AUTO_DISCOVERY,
    CONF_DISCOVERY_INTERVAL_DEFAULT,
    CONF_IPS_TO_REMOVE,
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
        )


class GoveeLocalApiCoordinator(DataUpdateCoordinator[list[GoveeDevice]]):
    """Govee light local coordinator."""

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

        config: GoveeLocalApiConfig = GoveeLocalApiConfig.from_config_entry(
            config_entry
        )

        self._controllers: list[GoveeController] = [
            GoveeController(
                loop=hass.loop,
                logger=_LOGGER,
                listening_addresses=source_ip,
                broadcast_address=CONF_MULTICAST_ADDRESS_DEFAULT,
                broadcast_port=CONF_TARGET_PORT_DEFAULT,
                listening_port=CONF_LISTENING_PORT_DEFAULT,
                discovery_enabled=config.auto_discovery,
                discovery_interval=CONF_DISCOVERY_INTERVAL_DEFAULT,
                discovered_callback=None,
                update_enabled=False,
            )
            for source_ip in source_ips
        ]

    async def start(self) -> None:
        """Start the Govee coordinator."""

        for controller in self._controllers:
            await controller.start()
            controller.send_update_message()

    async def set_discovery_callback(
        self, callback: Callable[[GoveeDevice, bool], bool]
    ) -> None:
        """Set discovery callback for automatic Govee light discovery."""

        for controller in self._controllers:
            controller.set_device_discovered_callback(callback)

    def enable_discovery(self, enable: bool) -> None:
        """Enable or disable automatic Govee light discovery."""
        for controller in self._controllers:
            controller.set_discovery_enabled(enable)

    def add_device_to_discovery_queue(self, ip: str) -> bool:
        """Add a device by IP address to discovery queue."""
        # The device is reachable through only one of the source IPs, so queue
        # it on every controller and report success if any of them accepted it.
        return any(
            controller.add_device_to_discovery_queue(ip)
            for controller in self._controllers
        )

    def remove_device_from_discovery_queue(self, ip: str) -> None:
        """Remove a device by IP address from manual discovery queue."""
        for controller in self._controllers:
            controller.remove_device_from_discovery_queue(ip)

    def remove_device(self, device: GoveeDevice) -> None:
        """Remove a device from the controllers."""
        for controller in self._controllers:
            controller.remove_device(device)

    def get_device_by_ip(self, ip: str) -> GoveeDevice | None:
        """Return a device by IP address."""
        for controller in self._controllers:
            if device := controller.get_device_by_ip(ip):
                return device
        return None

    def cleanup(self) -> list[asyncio.Event]:
        """Stop and cleanup the coordinator."""

        return [controller.cleanup() for controller in self._controllers]

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

    @property
    def devices(self) -> list[GoveeDevice]:
        """Return a list of discovered Govee devices."""

        devices: list[GoveeDevice] = []
        for controller in self._controllers:
            devices = devices + controller.devices
        return devices

    @property
    def discovery_queue(self) -> set[str]:
        """Return a set of devices in the discovery queue."""
        queue: set[str] = set()
        for controller in self._controllers:
            queue |= controller.discovery_queue
        return queue

    @property
    def discovery_enabled(self) -> bool:
        """Return if discovery is enabled."""
        return any(controller.discovery for controller in self._controllers)

    @override
    async def _async_update_data(self) -> list[GoveeDevice]:
        for controller in self._controllers:
            controller.send_update_message()
        return self.devices
