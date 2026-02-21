import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import switch

from . import ALPICOOL_BLE_COMPONENT_SCHEMA, AlpicoolBle, CONF_ALPICOOL_BLE_ID, alpicool_ble_ns

AlpicoolBleSwitch = alpicool_ble_ns.class_(
    "AlpicoolBleSwitch", switch.Switch, cg.Component
)

CONF_POWER = "power"
CONF_CONTROLS_LOCK = "controls_lock"

CONFIG_SCHEMA = ALPICOOL_BLE_COMPONENT_SCHEMA.extend(
    {
        cv.Optional(CONF_POWER): switch.switch_schema(
            AlpicoolBleSwitch,
            icon="mdi:power",
        ),
        cv.Optional(CONF_CONTROLS_LOCK): switch.switch_schema(
            AlpicoolBleSwitch,
            icon="mdi:lock",
        ),
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_ALPICOOL_BLE_ID])

    if CONF_POWER in config:
        sw = await switch.new_switch(config[CONF_POWER])
        cg.add(sw.set_parent(hub))
        cg.add(sw.set_is_power(True))
        cg.add(hub.set_power_switch(sw))

    if CONF_CONTROLS_LOCK in config:
        sw = await switch.new_switch(config[CONF_CONTROLS_LOCK])
        cg.add(sw.set_parent(hub))
        cg.add(sw.set_is_power(False))
        cg.add(hub.set_controls_lock_switch(sw))
