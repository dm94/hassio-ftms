"""The FTMS integration."""

import logging
import asyncio

import pyftms
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_SENSORS,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import DataCoordinator
from .models import FtmsData

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

_LOGGER = logging.getLogger(__name__)
logging.getLogger("pyftms").setLevel(_LOGGER.level)

type FtmsConfigEntry = ConfigEntry[FtmsData]


async def async_unload_entry(hass: HomeAssistant, entry: FtmsConfigEntry) -> bool:
    """Unload a config entry."""

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.ftms.disconnect()
        bluetooth.async_rediscover_address(hass, entry.runtime_data.ftms.address)

    return unload_ok


async def async_setup_entry(hass: HomeAssistant, entry: FtmsConfigEntry) -> bool:
    """Set up device from a config entry."""

    address: str = entry.data[CONF_ADDRESS]

    if not (srv_info := bluetooth.async_last_service_info(hass, address)):
        raise ConfigEntryNotReady(translation_key="device_not_found")

    def _on_disconnect(ftms_: pyftms.FitnessMachine) -> None:
        """Disconnect handler."""
        if ftms_.need_connect and hass.is_running:
            _LOGGER.debug("Device disconnected, scheduling reconnection...")
            coordinator.connection_lost()
            
            if not hasattr(_on_disconnect, "reload_scheduled"):
                _on_disconnect.reload_scheduled = True
                
                async def delayed_reload():
                    try:
                        await asyncio.sleep(5)
                        if hass.is_running:
                            entry_id = entry.entry_id
                            if hass.config_entries.async_get_entry(entry_id):
                                hass.config_entries.async_schedule_reload(entry_id)
                    except Exception as e:
                        _LOGGER.error("Error in delayed reload: %s", e)
                    finally:
                        delattr(_on_disconnect, "reload_scheduled")
                
                hass.async_create_task(delayed_reload())

    try:
        ftms = pyftms.get_client(
            srv_info.device,
            srv_info.advertisement,
            on_disconnect=_on_disconnect,
        )
    except pyftms.NotFitnessMachineError:
        raise ConfigEntryNotReady(translation_key="ftms_error")

    coordinator = DataCoordinator(hass, ftms)

    try:
        await asyncio.wait_for(ftms.connect(), timeout=10.0)
    except asyncio.TimeoutError:
        raise ConfigEntryNotReady(translation_key="connection_timeout")
    except BleakError as exc:
        if "BleakCharacteristicNotFoundError" in str(exc):
            _LOGGER.warning("Device does not support some characteristics, continuing anyway")
        else:
            _LOGGER.error("Connection error: %s", exc)
            raise ConfigEntryNotReady(translation_key="connection_failed") from exc

    assert ftms.machine_type.name

    try:
        _LOGGER.debug(f"Device Information: {ftms.device_info}")
        _LOGGER.debug(f"Machine type: {ftms.machine_type.name}")
        _LOGGER.debug(f"Available sensors: {ftms.available_properties}")
        
        try:
            _LOGGER.debug(f"Supported settings: {ftms.supported_settings}")
        except AttributeError:
            _LOGGER.debug("No supported settings available")
        
        try:
            _LOGGER.debug(f"Supported ranges: {ftms.supported_ranges}")
        except AttributeError:
            _LOGGER.debug("No supported ranges available")

    except Exception as e:
        _LOGGER.warning(f"Error getting device properties: {e}")

    unique_id = "".join(
        x for x in ftms.device_info.get("serial_number", address) if x.isalnum()
    ).lower()

    _LOGGER.debug(f"Registered new FTMS device. UniqueID is '{unique_id}'.")

    device_info = dr.DeviceInfo(
        connections={(dr.CONNECTION_BLUETOOTH, ftms.address)},
        identifiers={(DOMAIN, unique_id)},
        translation_key=ftms.machine_type.name.lower(),
        **ftms.device_info,
    )

    entry.runtime_data = FtmsData(
        entry_id=entry.entry_id,
        unique_id=unique_id,
        device_info=device_info,
        ftms=ftms,
        coordinator=coordinator,
        sensors=entry.options[CONF_SENSORS],
    )

    @callback
    def _async_on_ble_event(
        srv_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Update from a ble callback."""

        ftms.set_ble_device_and_advertisement_data(
            srv_info.device, srv_info.advertisement
        )

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_on_ble_event,
            BluetoothCallbackMatcher(address=address),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )

    # Platforms initialization
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_entry_update_handler))

    async def _async_hass_stop_handler(event: Event) -> None:
        """Close the connection."""

        await ftms.disconnect()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_hass_stop_handler)
    )

    return True


async def _async_entry_update_handler(
    hass: HomeAssistant, entry: FtmsConfigEntry
) -> None:
    """Options update handler."""

    if entry.options[CONF_SENSORS] != entry.runtime_data.sensors:
        hass.config_entries.async_schedule_reload(entry.entry_id)
