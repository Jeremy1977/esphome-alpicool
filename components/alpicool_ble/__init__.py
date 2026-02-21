import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import ble_client
from esphome.const import CONF_ID, CONF_THROTTLE

CODEOWNERS = ["@neftaly"]
DEPENDENCIES = ["ble_client"]
AUTO_LOAD = ["binary_sensor", "climate", "sensor", "select", "switch"]
MULTI_CONF = True

CONF_ALPICOOL_BLE_ID = "alpicool_ble_id"

alpicool_ble_ns = cg.esphome_ns.namespace("alpicool_ble")
AlpicoolBle = alpicool_ble_ns.class_(
    "AlpicoolBle",
    cg.PollingComponent,
    ble_client.BLEClientNode,
)

ALPICOOL_BLE_COMPONENT_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_ALPICOOL_BLE_ID): cv.use_id(AlpicoolBle),
    }
)

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(AlpicoolBle),
            cv.Optional(CONF_THROTTLE, default="10s"): cv.positive_time_period_milliseconds,
        }
    )
    .extend(ble_client.BLE_CLIENT_SCHEMA)
    .extend(cv.polling_component_schema("10s"))
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await ble_client.register_ble_node(var, config)
    cg.add(var.set_throttle(config[CONF_THROTTLE]))
