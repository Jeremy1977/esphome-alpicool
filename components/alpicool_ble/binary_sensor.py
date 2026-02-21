import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import binary_sensor
from esphome.const import DEVICE_CLASS_LOCK, DEVICE_CLASS_POWER

from . import ALPICOOL_BLE_COMPONENT_SCHEMA, AlpicoolBle, CONF_ALPICOOL_BLE_ID

CONF_POWERED_ON = "powered_on"
CONF_CONTROLS_LOCKED = "controls_locked"

CONFIG_SCHEMA = ALPICOOL_BLE_COMPONENT_SCHEMA.extend(
    {
        cv.Optional(CONF_POWERED_ON): binary_sensor.binary_sensor_schema(
            device_class=DEVICE_CLASS_POWER,
        ),
        cv.Optional(CONF_CONTROLS_LOCKED): binary_sensor.binary_sensor_schema(
            device_class=DEVICE_CLASS_LOCK,
        ),
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_ALPICOOL_BLE_ID])

    if CONF_POWERED_ON in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_POWERED_ON])
        cg.add(hub.set_powered_on_binary_sensor(sens))

    if CONF_CONTROLS_LOCKED in config:
        sens = await binary_sensor.new_binary_sensor(config[CONF_CONTROLS_LOCKED])
        cg.add(hub.set_controls_locked_binary_sensor(sens))
