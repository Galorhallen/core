"""Config flow for Govee light local."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_DISCOVERY_ENABLED = "discovery_enabled"
CONF_MANUAL_DEVICES = "manual_devices_ip"


class GoveeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for govee."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            # disovery_enabled = user_input[CONF_DISCOVERY_ENABLED]
            #  await self.async_set_unique_id(, raise_on_progress=False)
            # self._abort_if_unique_id_configured()
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DISCOVERY_ENABLED): cv.boolean,
                    vol.Optional(CONF_MANUAL_DEVICES): vol.All([cv.string]),
                },
            ),
        )


# async def _async_has_devices(hass: HomeAssistant) -> bool:
#     """Return if there are devices that can be discovered."""

#     adapter = await network.async_get_source_ip(hass, network.PUBLIC_TARGET_IP)

#     controller: GoveeController = GoveeController(
#         loop=hass.loop,
#         logger=_LOGGER,
#         listening_address=adapter,
#         broadcast_address=CONF_MULTICAST_ADDRESS_DEFAULT,
#         broadcast_port=CONF_TARGET_PORT_DEFAULT,
#         listening_port=CONF_LISTENING_PORT_DEFAULT,
#         discovery_enabled=True,
#         discovery_interval=1,
#         update_enabled=False,
#     )

#     await controller.start()

#     try:
#         async with asyncio.timeout(delay=5):
#             while not controller.devices:
#                 await asyncio.sleep(delay=1)
#     except TimeoutError:
#         _LOGGER.debug("No devices found")

#     devices_count = len(controller.devices)
#     controller.cleanup()

#     return devices_count > 0


# config_entry_flow.register_discovery_flow(
#     DOMAIN, "Govee light local", _async_has_devices
# )
