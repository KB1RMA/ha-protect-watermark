"""Config flow for UniFi Protect Watermark.

There's nothing to sign in to: the flow only picks which UniFi Protect config
entry to use.
"""

from __future__ import annotations

from typing import Any, override

import probatio

from homeassistant.config_entries import ConfigEntryState, ConfigFlow, ConfigFlowResult

# Home Assistant's selector registry decorator erases the class's generic type.
from homeassistant.helpers.selector import (
    ConfigEntrySelector,  # pyright: ignore[reportUnknownVariableType]
    ConfigEntrySelectorConfig,
)

from .const import CONF_PROTECT_ENTRY_ID, DOMAIN, PROTECT_DOMAIN


class ProtectWatermarkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pick the UniFi Protect console whose cameras to manage."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow started from the UI."""
        loaded = [
            entry
            for entry in self.hass.config_entries.async_entries(PROTECT_DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if not loaded:
            return self.async_abort(reason="no_protect")

        if user_input is None and len(loaded) == 1:
            user_input = {CONF_PROTECT_ENTRY_ID: loaded[0].entry_id}

        if user_input is not None:
            protect_entry_id: str = user_input[CONF_PROTECT_ENTRY_ID]
            protect_entry = self.hass.config_entries.async_get_entry(protect_entry_id)
            if protect_entry is None or protect_entry.domain != PROTECT_DOMAIN:
                return self.async_abort(reason="no_protect")
            await self.async_set_unique_id(protect_entry_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=protect_entry.title,
                data={CONF_PROTECT_ENTRY_ID: protect_entry_id},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_PROTECT_ENTRY_ID): ConfigEntrySelector(
                        ConfigEntrySelectorConfig(integration=PROTECT_DOMAIN)
                    )
                }
            ),
        )
