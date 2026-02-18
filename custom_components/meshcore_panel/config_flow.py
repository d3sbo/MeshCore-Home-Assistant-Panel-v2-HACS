"""Config flow for MeshCore Panel."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_MY_REPEATER_PUBKEY,
    CONF_MY_NAME,
    CONF_GREET_ENABLED,
    CONF_CLEANUP_ENABLED,
    DEFAULT_MAX_GREET_HOPS,
    DEFAULT_GREET_CHANNEL,
    DEFAULT_CLEANUP_DAYS,
)


class MeshCorePanelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MeshCore Panel."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate input
            if not user_input.get(CONF_MY_REPEATER_PUBKEY):
                errors[CONF_MY_REPEATER_PUBKEY] = "pubkey_required"
            else:
                return self.async_create_entry(
                    title="MeshCore Panel",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_MY_REPEATER_PUBKEY): str,
                vol.Optional(CONF_MY_NAME, default="MyRepeater"): str,
                vol.Optional(CONF_GREET_ENABLED, default=True): bool,
                vol.Optional(CONF_CLEANUP_ENABLED, default=True): bool,
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return MeshCorePanelOptionsFlow(config_entry)


class MeshCorePanelOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for MeshCore Panel."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_MY_REPEATER_PUBKEY,
                    default=self.config_entry.data.get(CONF_MY_REPEATER_PUBKEY, ""),
                ): str,
                vol.Optional(
                    CONF_MY_NAME,
                    default=self.config_entry.data.get(CONF_MY_NAME, "MyRepeater"),
                ): str,
                vol.Optional(
                    CONF_GREET_ENABLED,
                    default=self.config_entry.data.get(CONF_GREET_ENABLED, True),
                ): bool,
                vol.Optional(
                    CONF_CLEANUP_ENABLED,
                    default=self.config_entry.data.get(CONF_CLEANUP_ENABLED, True),
                ): bool,
            }),
        )
