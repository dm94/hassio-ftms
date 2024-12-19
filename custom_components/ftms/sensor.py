"""FTMS integration sensor platform."""

import logging
from enum import Enum
from typing import Final

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTime,
    PERCENTAGE,
    UnitOfFrequency,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyftms import MovementDirection, TrainingStatusCode
from pyftms.client import const as c

from . import FtmsConfigEntry
from .entity import FtmsEntity

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS: Final = {
    "speed_instant": SensorEntityDescription(
        key="speed_instant",
        translation_key="speed_instant",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "speed_average": SensorEntityDescription(
        key="speed_average",
        translation_key="speed_average",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "speed_maximum": SensorEntityDescription(
        key="speed_maximum",
        translation_key="speed_maximum",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    
    "distance_total": SensorEntityDescription(
        key="distance_total",
        translation_key="distance_total",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    
    "cadence": SensorEntityDescription(
        key="cadence",
        translation_key="cadence",
        native_unit_of_measurement=UnitOfFrequency.REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "cadence_average": SensorEntityDescription(
        key="cadence_average",
        translation_key="cadence_average",
        native_unit_of_measurement=UnitOfFrequency.REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "cadence_maximum": SensorEntityDescription(
        key="cadence_maximum",
        translation_key="cadence_maximum",
        native_unit_of_measurement=UnitOfFrequency.REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    
    "energy_total": SensorEntityDescription(
        key="energy_total",
        translation_key="energy_total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "energy_per_hour": SensorEntityDescription(
        key="energy_per_hour",
        translation_key="energy_per_hour",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    
    "power_output": SensorEntityDescription(
        key="power_output",
        translation_key="power_output",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    
    "time_elapsed": SensorEntityDescription(
        key="time_elapsed",
        translation_key="time_elapsed",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "time_remaining": SensorEntityDescription(
        key="time_remaining",
        translation_key="time_remaining",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    
    "heart_rate": SensorEntityDescription(
        key="heart_rate",
        translation_key="heart_rate",
        native_unit_of_measurement=UnitOfFrequency.BEATS_PER_MINUTE,
        device_class=SensorDeviceClass.HEART_RATE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    
    "step_count": SensorEntityDescription(
        key="step_count",
        translation_key="step_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "cadence": SensorEntityDescription(
        key="cadence",
        translation_key="cadence",
        native_unit_of_measurement=UnitOfFrequency.REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    
    "inclination": SensorEntityDescription(
        key="inclination",
        translation_key="inclination",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "elevation_gain": SensorEntityDescription(
        key="elevation_gain",
        translation_key="elevation_gain",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    
    "training_status": SensorEntityDescription(
        key="training_status",
        translation_key="training_status",
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FtmsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up FTMS sensors from config entry."""
    data = entry.runtime_data

    entities = []
    for sensor_key in data.sensors:
        if sensor_description := SENSOR_DESCRIPTIONS.get(sensor_key):
            entities.append(
                FtmsSensorEntity(
                    entry=entry,
                    description=sensor_description,
                )
            )
        else:
            _LOGGER.warning(f"Unknown sensor type: {sensor_key}")

    if entities:
        async_add_entities(entities)


class FtmsSensorEntity(FtmsEntity, SensorEntity):
    """Representation of FTMS sensors."""

    def __init__(self, entry: FtmsConfigEntry, description: SensorEntityDescription) -> None:
        """Initialize the sensor."""
        super().__init__(entry, description)
        self._attr_native_value = None
        self._update_value()

    def _update_value(self) -> None:
        """Update the sensor value."""
        try:
            value = getattr(self.ftms, self.key, None)
            if isinstance(value, Enum):
                value = value.name.lower()
            self._attr_native_value = value
        except Exception as e:
            _LOGGER.debug(f"Error updating sensor {self.key}: {e}")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_value()
        self.async_write_ha_state()
