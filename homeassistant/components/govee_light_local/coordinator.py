"""Coordinator for Govee light local."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Self, override

from govee_local_api import GoveeController, GoveeDevice

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_AUTO_DISCOVERY,
    CONF_DISCOVERY_INTERVAL_DEFAULT,
    CONF_LISTENING_PORT_DEFAULT,
    CONF_MANUAL_DEVICES,
    CONF_MULTICAST_ADDRESS_DEFAULT,
    CONF_TARGET_PORT_DEFAULT,
    DOMAIN,
    SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type GoveeLocalConfigEntry = ConfigEntry[GoveeLocalApiCoordinator]


@dataclass
class GoveeLocalApiConfig:
    """Govee light local configuration."""

    auto_discovery: bool
    manual_devices: set[str]

    @classmethod
    def from_config_entry(cls, config_entry: GoveeLocalConfigEntry) -> Self:
        """Return Govee light local configuration from config entry."""

        options = config_entry.options

        return cls(
            options.get(CONF_AUTO_DISCOVERY, True),
            set(options.get(CONF_MANUAL_DEVICES, [])),
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

        config: GoveeLocalApiConfig = GoveeLocalApiConfig.from_config_entry(
            config_entry
        )

        # A single controller listens on every enabled source IP: it opens one
        # transport per address internally, so there is no need for one
        # controller per network interface.
        self._controller = GoveeController(
            loop=hass.loop,
            logger=_LOGGER,
            listening_addresses=sorted(source_ips),
            broadcast_address=CONF_MULTICAST_ADDRESS_DEFAULT,
            broadcast_port=CONF_TARGET_PORT_DEFAULT,
            listening_port=CONF_LISTENING_PORT_DEFAULT,
            discovery_enabled=config.auto_discovery,
            discovery_interval=CONF_DISCOVERY_INTERVAL_DEFAULT,
            discovered_callback=None,
            update_enabled=False,
        )

    async def start(self) -> None:
        """Start the Govee coordinator."""
        await self._controller.start()
        self._controller.send_update_message()

    async def set_discovery_callback(
        self, discovered_callback: Callable[[GoveeDevice, bool], bool]
    ) -> None:
        """Set discovery callback for automatic Govee light discovery."""
        self._controller.set_device_discovered_callback(discovered_callback)

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

    @property
    def manual_device_ips(self) -> set[str]:
        """Return the IPs the controller tracks as manually added.

        A queued IP moves into ``devices`` with ``is_manual`` set once the
        device answers, and eviction puts it back in the queue, so the two are
        disjoint and their union mirrors the configured manual devices.
        """
        return {device.ip for device in self.devices if device.is_manual} | set(
            self.discovery_queue
        )

    @callback
    def async_remove_manual_device(self, ip: str) -> None:
        """Remove a manually added device and its registry entry."""
        if device := self.get_device_by_ip(ip):
            device_registry = dr.async_get(self.hass)
            if entry := device_registry.async_get_device_by_identifier(
                (DOMAIN, device.fingerprint), self.config_entry.entry_id
            ):
                # Removing the device cascades to its entities.
                device_registry.async_remove_device(entry.id)
            self.remove_device(device)
        self.remove_device_from_discovery_queue(ip)

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

    @override
    async def _async_update_data(self) -> list[GoveeDevice]:
        self._controller.send_update_message()
        return self.devices
