"""Govee light local sensor platform."""

from __future__ import annotations

from govee_local_api import GoveeDevice

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import GoveeLocalApiCoordinator, GoveeLocalConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GoveeLocalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Govee sensor entities."""
    coordinator = config_entry.runtime_data

    async_add_entities(
        entity
        for device in coordinator.devices
        for entity in (
            GoveeSensor(coordinator, device),
            GoveeInterfaceSensor(coordinator, device),
        )
    )

    coordinator.new_device_callbacks.append(
        lambda device: async_add_entities(
            [
                GoveeSensor(coordinator, device),
                GoveeInterfaceSensor(coordinator, device),
            ]
        )
    )


class GoveeBaseSensor(CoordinatorEntity[GoveeLocalApiCoordinator], SensorEntity):
    """Base class for Govee diagnostic sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: GoveeLocalApiCoordinator,
        device: GoveeDevice,
        key: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device = device
        self._attr_translation_key = key
        self._attr_unique_id = f"{device.fingerprint}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.fingerprint)},
            name=device.sku,
            manufacturer=MANUFACTURER,
            model_id=device.sku,
            serial_number=device.fingerprint,
        )


class GoveeSensor(GoveeBaseSensor):
    """Govee IP address sensor."""

    def __init__(
        self,
        coordinator: GoveeLocalApiCoordinator,
        device: GoveeDevice,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device, "ip_address")

    @property
    def native_value(self) -> str:
        """Return the IP address of the device."""
        return self._device.ip


class GoveeInterfaceSensor(GoveeBaseSensor):
    """Govee listening interface sensor."""

    def __init__(
        self,
        coordinator: GoveeLocalApiCoordinator,
        device: GoveeDevice,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device, "listening_interface")

    @property
    def native_value(self) -> str | None:
        """Return the listening address for this device's interface."""
        return self.coordinator.get_device_listening_address(self._device)
