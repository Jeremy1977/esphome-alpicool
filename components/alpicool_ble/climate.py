import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import climate
from esphome.const import CONF_ID

from . import ALPICOOL_BLE_COMPONENT_SCHEMA, AlpicoolBle, CONF_ALPICOOL_BLE_ID, alpicool_ble_ns

AlpicoolClimate = alpicool_ble_ns.class_(
    "AlpicoolClimate", climate.Climate, cg.Component
)

CONFIG_SCHEMA = climate.climate_schema(AlpicoolClimate).extend(
    ALPICOOL_BLE_COMPONENT_SCHEMA
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await climate.register_climate(var, config)

    hub = await cg.get_variable(config[CONF_ALPICOOL_BLE_ID])
    cg.add(var.set_parent(hub))
    cg.add(hub.set_climate(var))
