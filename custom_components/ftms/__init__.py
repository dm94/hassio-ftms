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
        if ftms_.need_connect:
            _LOGGER.debug("Device disconnected")
            coordinator.connection_lost()

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
        if "BleakCharacteristicNotFoundError" not in str(exc):
            _LOGGER.error("Connection error: %s", exc)
            raise ConfigEntryNotReady(translation_key="connection_failed") from exc
        _LOGGER.warning("Some characteristics not found, continuing with limited functionality")

    available_features = set()
    try:
        reported_features = ftms.available_properties
        _LOGGER.debug(f"Device reported features: {reported_features}")

        for feature in reported_features:
            try:
                if hasattr(ftms, feature):
                    value = getattr(ftms, feature)
                    if value is not None or isinstance(value, (int, float, str, bool)):
                        available_features.add(feature)
                        _LOGGER.debug(f"Verified feature {feature} is available")
            except Exception as e:
                _LOGGER.debug(f"Feature {feature} not accessible: {e}")

    except Exception as e:
        _LOGGER.warning(f"Error verifying features: {e}")

    if not available_features:
        _LOGGER.warning("No features available on device")
    else:
        _LOGGER.info(f"Available features: {sorted(available_features)}")

    unique_id = "".join(
        x for x in ftms.device_info.get("serial_number", address) if x.isalnum()
    ).lower()

    device_info = dr.DeviceInfo(
        connections={(dr.CONNECTION_BLUETOOTH, ftms.address)},
        identifiers={(DOMAIN, unique_id)},
        translation_key=ftms.machine_type.name.lower(),
        **ftms.device_info,
    )

    selected_sensors = entry.options.get(CONF_SENSORS, [])
    valid_sensors = [s for s in selected_sensors if s in available_features]

    if not valid_sensors and selected_sensors:
        _LOGGER.warning(
            "None of the selected sensors %s are available. Available sensors: %s",
            selected_sensors,
            sorted(available_features)
        )

    entry.runtime_data = FtmsData(
        entry_id=entry.entry_id,
        unique_id=unique_id,
        device_info=device_info,
        ftms=ftms,
        coordinator=coordinator,
        sensors=valid_sensors,
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
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_entry_update_handler))

    return True


async def _async_entry_update_handler(
    hass: HomeAssistant, entry: FtmsConfigEntry
) -> None:
    """Options update handler."""

    if entry.options[CONF_SENSORS] != entry.runtime_data.sensors:
        hass.config_entries.async_schedule_reload(entry.entry_id)
