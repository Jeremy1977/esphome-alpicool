import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import select
from esphome.const import CONF_ID, ENTITY_CATEGORY_CONFIG, ICON_THERMOMETER

from . import ALPICOOL_BLE_COMPONENT_SCHEMA, AlpicoolBle, CONF_ALPICOOL_BLE_ID, alpicool_ble_ns

AlpicoolBleSelect = alpicool_ble_ns.class_(
    "AlpicoolBleSelect", select.Select, cg.Component
)

CONF_RUN_MODE = "run_mode"
CONF_BATTERY_SAVER = "battery_saver"

CONFIG_SCHEMA = ALPICOOL_BLE_COMPONENT_SCHEMA.extend(
    {
        cv.Optional(CONF_RUN_MODE): select.select_schema(
            AlpicoolBleSelect,
            entity_category=ENTITY_CATEGORY_CONFIG,
            icon="mdi:speedometer",
        ),
        cv.Optional(CONF_BATTERY_SAVER): select.select_schema(
            AlpicoolBleSelect,
            entity_category=ENTITY_CATEGORY_CONFIG,
            icon="mdi:battery-alert",
        ),
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_ALPICOOL_BLE_ID])

    if CONF_RUN_MODE in config:
        sel = await select.new_select(config[CONF_RUN_MODE], options=["Max", "Eco"])
        cg.add(sel.set_parent(hub))
        cg.add(sel.set_select_type(0))
        cg.add(hub.set_run_mode_select(sel))

    if CONF_BATTERY_SAVER in config:
        sel = await select.new_select(config[CONF_BATTERY_SAVER], options=["Low", "Mid", "High"])
        cg.add(sel.set_parent(hub))
        cg.add(sel.set_select_type(1))
        cg.add(hub.set_battery_saver_select(sel))
