"""Data coordinator for receiving FTMS events."""

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.exceptions import ConfigEntryNotReady
from pyftms import FitnessMachine, FtmsEvents

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class DataCoordinator(DataUpdateCoordinator[FtmsEvents]):
    """FTMS events coordinator."""

    def __init__(self, hass: HomeAssistant, ftms: FitnessMachine) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        
        self.ftms = ftms
        self._last_event: FtmsEvents | None = None
        self._connected = False
        self._last_successful_update = None

        def _on_ftms_event(data: FtmsEvents):
            """Handle FTMS events."""
            try:
                _LOGGER.debug(f"Event data: {data}")
                self._last_event = data
                self._connected = True
                self.async_set_updated_data(data)
            except Exception as e:
                _LOGGER.error(f"Error processing FTMS event: {e}")

        self.ftms.set_callback(_on_ftms_event)

    async def _async_update_data(self) -> FtmsEvents:
        """Update data."""
        try:
            if not self._connected:
                _LOGGER.debug("Attempting to connect for data update...")
                try:
                    await self.ftms.connect()
                    self._connected = True
                    _LOGGER.debug("Connected successfully")
                except Exception as e:
                    if "BleakCharacteristicNotFoundError" in str(e):
                        self._connected = True
                        _LOGGER.debug("Device does not support some characteristics, continuing anyway")
                    else:
                        _LOGGER.debug(f"Connection attempt failed: {e}")
                        return self._last_event or FtmsEvents()

            try:
                if self._last_event:
                    return self._last_event
                return FtmsEvents()
            finally:
                try:
                    await self.ftms.disconnect()
                    _LOGGER.debug("Disconnected after data update")
                except Exception as e:
                    _LOGGER.debug(f"Error during disconnect: {e}")
                self._connected = False

        except Exception as e:
            _LOGGER.error(f"Error in update cycle: {e}")
            return self._last_event or FtmsEvents()

    def connection_lost(self):
        """Mark connection as lost."""
        if self._connected:
            self._connected = False
            _LOGGER.debug("Connection marked as lost")

    def is_connected(self) -> bool:
        """Return connection status."""
        return self._connected
