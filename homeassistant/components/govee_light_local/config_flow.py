"""Config flow for Govee light local."""

import asyncio
from contextlib import suppress
from ipaddress import AddressValueError, IPv4Address
import logging
from typing import Any, override

from govee_local_api import GoveeController
import voluptuous as vol

from homeassistant.components import onboarding
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import async_get_source_ips
from .const import (
    CONF_AUTO_DISCOVERY,
    CONF_DEVICE_IP,
    CONF_IPS_TO_REMOVE,
    CONF_LISTENING_PORT_DEFAULT,
    CONF_MANUAL_DEVICES,
    CONF_MULTICAST_ADDRESS_DEFAULT,
    CONF_TARGET_PORT_DEFAULT,
    DISCOVERY_TIMEOUT,
    DOMAIN,
)
from .coordinator import GoveeLocalApiConfig

_LOGGER = logging.getLogger(__name__)


async def _async_has_devices(hass: HomeAssistant) -> bool:
    """Return if there are devices that can be discovered."""

    source_ips = sorted(await async_get_source_ips(hass))
    if not source_ips:
        _LOGGER.debug("No enabled IPv4 source IPs to discover on")
        return False

    # One controller listens on every enabled source IP at once, so a single
    # discovery round covers all network interfaces.
    controller: GoveeController = GoveeController(
        loop=hass.loop,
        logger=_LOGGER,
        listening_addresses=source_ips,
        broadcast_address=CONF_MULTICAST_ADDRESS_DEFAULT,
        broadcast_port=CONF_TARGET_PORT_DEFAULT,
        listening_port=CONF_LISTENING_PORT_DEFAULT,
        discovery_enabled=True,
        discovery_interval=1,
        update_enabled=False,
    )

    try:
        _LOGGER.debug("Starting discovery with IPs %s", source_ips)
        await controller.start()
    except OSError as ex:
        _LOGGER.error("Start failed on IPs %s, errno: %d", source_ips, ex.errno)
        return False

    try:
        async with asyncio.timeout(delay=DISCOVERY_TIMEOUT):
            while not controller.devices:
                await asyncio.sleep(delay=1)
    except TimeoutError:
        _LOGGER.debug("No devices found with IPs %s", source_ips)

    devices_count = len(controller.devices)
    cleanup_complete: asyncio.Event = controller.cleanup()
    with suppress(TimeoutError):
        await asyncio.wait_for(cleanup_complete.wait(), 1)

    return devices_count > 0


class GoveeConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Govee light local."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""

        await self.async_set_unique_id(DOMAIN)

        if user_input is not None:
            if user_input.get(CONF_AUTO_DISCOVERY):
                return await self.async_step_discovery_confirm()
            return self.async_create_entry(
                title="", data={}, options={CONF_AUTO_DISCOVERY: False}
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AUTO_DISCOVERY,
                        default=True,
                    ): BooleanSelector(),
                }
            ),
        )

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setup."""
        if user_input is not None or not onboarding.async_is_onboarded(self.hass):
            if not await _async_has_devices(self.hass):
                return self.async_abort(reason="no_devices_found")
            return self.async_create_entry(
                title="", data={}, options={CONF_AUTO_DISCOVERY: True}
            )

        self._set_confirm_only()
        return self.async_show_form(step_id="discovery_confirm", last_step=True)

    @staticmethod
    @callback
    @override
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> GoveeOptionsFlowHandler:
        """Get the options flow."""
        return GoveeOptionsFlowHandler()


class GoveeOptionsFlowHandler(OptionsFlow):
    """Handle a option flow for Govee light local."""

    def _updated_options(self, **changes: Any) -> dict[str, Any]:
        """Return the entry options with the given keys replaced.

        Every step returns the complete resulting options, so the update
        listener can reconcile from them without being told what changed.
        """
        return {**self.config_entry.options, **changes}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_device",
                "remove_device",
                "configure_auto_discovery",
            ],
        )

    async def async_step_configure_auto_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure auto discovery."""
        config: GoveeLocalApiConfig = GoveeLocalApiConfig.from_config_entry(
            self.config_entry
        )

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=self._updated_options(
                    **{CONF_AUTO_DISCOVERY: user_input[CONF_AUTO_DISCOVERY]}
                ),
            )

        return self.async_show_form(
            step_id="configure_auto_discovery",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AUTO_DISCOVERY, default=config.auto_discovery
                    ): BooleanSelector(),
                }
            ),
            last_step=True,
        )

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a device by IP address."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        if user_input is not None:
            user_ip = user_input[CONF_DEVICE_IP]
            try:
                IPv4Address(user_ip)
            except AddressValueError:
                errors["base"] = "invalid_ip"
                placeholders["ip"] = user_ip
            else:
                config = GoveeLocalApiConfig.from_config_entry(self.config_entry)
                return self.async_create_entry(
                    title="",
                    data=self._updated_options(
                        **{
                            CONF_MANUAL_DEVICES: sorted(
                                config.manual_devices | {user_ip}
                            )
                        }
                    ),
                )

        return self.async_show_form(
            step_id="add_device",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE_IP): cv.string}),
            errors=errors,
            description_placeholders=placeholders,
            last_step=True,
        )

    async def async_step_remove_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a manually added device."""
        # The picker is built from the running controller, which is only
        # available while the entry is loaded.
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        config = GoveeLocalApiConfig.from_config_entry(self.config_entry)

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=self._updated_options(
                    **{
                        CONF_MANUAL_DEVICES: sorted(
                            config.manual_devices - set(user_input[CONF_IPS_TO_REMOVE])
                        )
                    }
                ),
            )

        coordinator = self.config_entry.runtime_data

        manual_devices = [
            *(
                SelectOptionDict(label=f"{device.sku} ({device.ip})", value=device.ip)
                for device in coordinator.devices
                if device.is_manual
            ),
            *(
                SelectOptionDict(label=ip, value=ip)
                for ip in coordinator.discovery_queue
            ),
        ]

        if not manual_devices:
            return self.async_abort(reason="no_devices")

        option_schema = {
            vol.Required(CONF_IPS_TO_REMOVE): SelectSelector(
                SelectSelectorConfig(
                    options=manual_devices,
                    custom_value=False,
                    mode=SelectSelectorMode.DROPDOWN,
                    multiple=True,
                )
            ),
        }

        return self.async_show_form(
            step_id="remove_device",
            data_schema=vol.Schema(option_schema),
            last_step=True,
        )
