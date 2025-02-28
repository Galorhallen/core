"""Config flow for Govee light local."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from contextlib import suppress
import logging
from typing import Any, Final

from govee_local_api import GoveeController, GoveeDevice
import voluptuous as vol

from homeassistant.components import network
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, selector
from homeassistant.helpers.config_entry_flow import DiscoveryFlowHandler

from .const import (
    CONF_OPTION_IMPORT_MODE,
    CONF_LISTENING_PORT_DEFAULT,
    CONF_MULTICAST_ADDRESS_DEFAULT,
    CONF_OPTION_AVAILABLE_SEGMENTS,
    CONF_OPTION_CURRENT_GROUP,
    CONF_OPTION_DEVICE,
    CONF_OPTION_GROUP_COUNT,
    CONF_OPTION_GROUPS,
    CONF_OPTION_IMPORT_STRIP,
    CONF_OPTION_SEGMENTS,
    CONF_OPTION_SEGMENTS_COUNT,
    CONF_TARGET_PORT_DEFAULT,
    DISCOVERY_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

IMPORT_MODE: Final[set[str]] = {"all_segments", "segments_group", "no_segments"}


async def _async_has_devices(hass: HomeAssistant) -> bool:
    """Return if there are devices that can be discovered."""

    adapter = await network.async_get_source_ip(hass, network.PUBLIC_TARGET_IP)

    controller: GoveeController = GoveeController(
        loop=hass.loop,
        logger=_LOGGER,
        listening_address=adapter,
        broadcast_address=CONF_MULTICAST_ADDRESS_DEFAULT,
        broadcast_port=CONF_TARGET_PORT_DEFAULT,
        listening_port=CONF_LISTENING_PORT_DEFAULT,
        discovery_enabled=True,
        discovery_interval=1,
        update_enabled=False,
    )

    try:
        await controller.start()
    except OSError as ex:
        _LOGGER.error("Start failed, errno: %d", ex.errno)
        return False

    try:
        async with asyncio.timeout(delay=DISCOVERY_TIMEOUT):
            while not controller.devices:
                await asyncio.sleep(delay=1)
    except TimeoutError:
        _LOGGER.debug("No devices found")

    devices_count = len(controller.devices)
    cleanup_complete: asyncio.Event = controller.cleanup()
    with suppress(TimeoutError):
        await asyncio.wait_for(cleanup_complete.wait(), 1)

    return devices_count > 0


class GoveeDiscoveryFlowHandler(DiscoveryFlowHandler[Awaitable[bool]], domain=DOMAIN):
    """Govee discovery flow that callsback."""

    def __init__(self) -> None:
        """Init discovery flow."""
        super().__init__(DOMAIN, "Govee light local", _async_has_devices)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlowHandler:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    """Handle a option flow for Govee light local."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        super().__init__()

        self._config_entry = config_entry
        self._options = {}
        self._device: GoveeDevice | None = None

    async def async_step_groups(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            schema = vol.Schema(
                {
                    vol.Required(
                        CONF_OPTION_IMPORT_STRIP, default=True
                    ): selector.BooleanSelector(),
                    vol.Required(CONF_OPTION_GROUP_COUNT, default=1): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=1, max=self._options[CONF_OPTION_SEGMENTS_COUNT]),
                    ),
                }
            )
            return self.async_show_form(
                step_id="groups",
                data_schema=self.add_suggested_values_to_schema(schema, self._options),
                description_placeholders={"device": f"{self._device.sku}"},
            )

        self._options[CONF_OPTION_IMPORT_STRIP] = user_input[CONF_OPTION_IMPORT_STRIP]
        self._options[CONF_OPTION_GROUP_COUNT] = user_input[CONF_OPTION_GROUP_COUNT]
        self._options[CONF_OPTION_AVAILABLE_SEGMENTS] = set(
            range(1, self._options[CONF_OPTION_SEGMENTS_COUNT] + 1)
        )
        self._options[CONF_OPTION_GROUPS] = [
            {} for i in range(self._options[CONF_OPTION_GROUP_COUNT])
        ]
        self._options[CONF_OPTION_CURRENT_GROUP] = 0

        return await self.async_step_segments()

    async def async_step_segments(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        if user_input is not None:
            segments: set[int] = set(user_input[CONF_OPTION_SEGMENTS])
            self._options[CONF_OPTION_AVAILABLE_SEGMENTS] -= segments
            current_group = self._options[CONF_OPTION_CURRENT_GROUP]
            self._options[CONF_OPTION_GROUPS][current_group] = segments
            self._options[CONF_OPTION_CURRENT_GROUP] += 1

            if (
                self._options[CONF_OPTION_CURRENT_GROUP]
                == self._options[CONF_OPTION_GROUP_COUNT]
            ):
                return self.async_create_entry(data=self._options)

        schema = vol.Schema(
            {
                vol.Required(CONF_OPTION_SEGMENTS): cv.multi_select(
                    self._options[CONF_OPTION_AVAILABLE_SEGMENTS]
                ),
            }
        )

        current_group = self._options[CONF_OPTION_CURRENT_GROUP]
        is_last: bool = (
            self._options[CONF_OPTION_CURRENT_GROUP]
            == self._options[CONF_OPTION_GROUP_COUNT] - 1
        )
        return self.async_show_form(
            step_id="segments",
            data_schema=schema,
            description_placeholders={"group": f"Group {current_group}"},
            last_step=is_last,
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        coordinator = self._config_entry.runtime_data
        devices = {
            d.fingerprint: f"{d.sku} ({d.capabilities.segments_count} segments)"
            for d in coordinator.devices
            if d.capabilities.segments_count > 1
        }

        if user_input is not None:
            self._options[CONF_OPTION_IMPORT_MODE] = user_input[CONF_OPTION_IMPORT_MODE]
            self._options[CONF_OPTION_DEVICE] = user_input[CONF_OPTION_DEVICE]
            self._device = coordinator.get_device_by_fingerprint(
                user_input[CONF_OPTION_DEVICE]
            )
            self._options[CONF_OPTION_SEGMENTS_COUNT] = (
                self._device.capabilities.segments_count
            )
            if user_input[CONF_OPTION_IMPORT_MODE] == "segments_group":
                return await self.async_step_groups()
            return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema(
            {
                vol.Optional("device"): vol.In(devices),
                vol.Required(CONF_OPTION_IMPORT_MODE, default="segments_group"): vol.In(
                    IMPORT_MODE
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
