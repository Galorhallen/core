"""The Govee Light local integration."""

import asyncio
from contextlib import suppress
from errno import EADDRINUSE
from ipaddress import IPv4Address
import logging

from govee_local_api.controller import LISTENING_PORT

from homeassistant.components import network
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import EventDeviceRegistryUpdatedData

from .const import CONF_MANUAL_DEVICES, DISCOVERY_TIMEOUT, DOMAIN
from .coordinator import (
    GoveeLocalApiConfig,
    GoveeLocalApiCoordinator,
    GoveeLocalConfigEntry,
)

PLATFORMS: list[Platform] = [Platform.LIGHT]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: GoveeLocalConfigEntry) -> bool:
    """Set up Govee light local from a config entry."""

    source_ips = await async_get_source_ips(hass)
    _LOGGER.debug("Enabled source IPs: %s", source_ips)

    if not source_ips:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="no_source_ips"
        )

    config: GoveeLocalApiConfig = GoveeLocalApiConfig.from_config_entry(entry)

    coordinator: GoveeLocalApiCoordinator = GoveeLocalApiCoordinator(
        hass=hass, config_entry=entry, source_ips=source_ips
    )

    async def await_cleanup() -> None:
        cleanup_complete: asyncio.Event = coordinator.cleanup()
        with suppress(TimeoutError):
            await asyncio.wait_for(cleanup_complete.wait(), 1)

    @callback
    def _async_device_removed(event: Event[EventDeviceRegistryUpdatedData]) -> None:
        """Forget a deleted device and unconfigure it if it was manual."""
        if event.data["action"] != "remove":
            return
        device_info = event.data["device"]
        if device_info["config_entry_id"] != entry.entry_id:
            return

        fingerprints = {
            identifier[1]
            for identifier in device_info["identifiers"]
            if identifier[0] == DOMAIN
        }
        # The device is still known to the controller at this point, which is
        # what lets us map the fingerprint back to its IP.
        removed = [
            device
            for device in coordinator.devices
            if device.fingerprint in fingerprints
        ]
        removed_ips = {device.ip for device in removed}
        # A device left in the controller answers the next scan as an already
        # known device, so the platform would never recreate its entity.
        for device in removed:
            coordinator.remove_device(device)

        config = GoveeLocalApiConfig.from_config_entry(entry)
        if (remaining := config.manual_devices - removed_ips) == config.manual_devices:
            return

        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, CONF_MANUAL_DEVICES: sorted(remaining)},
        )

    entry.async_on_unload(await_cleanup)
    entry.async_on_unload(entry.add_update_listener(update_options_listener))
    entry.async_on_unload(
        hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, _async_device_removed)
    )

    for device in config.manual_devices:
        coordinator.add_device_to_discovery_queue(device)

    try:
        await coordinator.start()
    except OSError as ex:
        if ex.errno != EADDRINUSE:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="cannot_start",
                translation_placeholders={"error": ex.strerror or str(ex)},
            ) from ex
        _LOGGER.error("Port %s already in use", LISTENING_PORT)
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="port_in_use",
            translation_placeholders={"port": LISTENING_PORT},
        ) from ex

    await coordinator.async_config_entry_first_refresh()

    if config.auto_discovery:
        try:
            async with asyncio.timeout(delay=DISCOVERY_TIMEOUT):
                while not coordinator.devices:
                    await asyncio.sleep(delay=1)
        except TimeoutError as ex:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN, translation_key="no_devices_found"
            ) from ex

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def update_options_listener(
    hass: HomeAssistant, config_entry: GoveeLocalConfigEntry
) -> None:
    """Reconcile the controller with the configured options.

    Options describe the desired set of manual devices, so the listener diffs
    them against what the controller currently tracks. This is idempotent and
    never writes back to the entry.
    """
    coordinator: GoveeLocalApiCoordinator = config_entry.runtime_data
    config: GoveeLocalApiConfig = GoveeLocalApiConfig.from_config_entry(config_entry)

    for ip in config.manual_devices:
        # Re-queueing a known IP would strand it there: the queue is only
        # drained when a device with a new fingerprint answers.
        if (
            ip not in coordinator.discovery_queue
            and coordinator.get_device_by_ip(ip) is None
        ):
            coordinator.add_device_to_discovery_queue(ip)

    # The difference is a new set, so removing entries below cannot mutate what
    # we are iterating over.
    for ip in coordinator.manual_device_ips - config.manual_devices:
        coordinator.async_remove_manual_device(ip)

    if coordinator.discovery_enabled != config.auto_discovery:
        coordinator.enable_discovery(config.auto_discovery)


async def async_unload_entry(hass: HomeAssistant, entry: GoveeLocalConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: GoveeLocalConfigEntry,
    device_entry: dr.AnyDeviceEntry,
) -> bool:
    """Allow removing a device.

    The actual cleanup is done in the device registry event.
    """
    return True


async def async_get_source_ips(
    hass: HomeAssistant,
) -> set[str]:
    """Get the source ips for Govee local."""
    source_ips = await network.async_get_enabled_source_ips(hass)
    return {
        str(source_ip) for source_ip in source_ips if isinstance(source_ip, IPv4Address)
    }
