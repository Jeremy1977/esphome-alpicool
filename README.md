# esphome-alpicool

ESPHome external component for Alpicool portable fridges over BLE.

## Supported models

Should work with Alpicool fridges that use the [Alpicool app](https://apps.apple.com/us/app/alpicool/id1364824375). Tested on a CX40; other models are untested but likely candidates include the C, CF, CX, ECX, T, TW, TWW, X, and TAW series.

## Features

- Climate entity (thermostat control)
- Temperature, battery %, and battery voltage sensors
- Power and controls lock switches
- Run mode (Max/Eco) and battery saver selects

## Usage

```yaml
external_components:
  - source: github://neftaly/esphome-alpicool

esp32_ble_tracker:

ble_client:
  - mac_address: "XX:XX:XX:XX:XX:XX"
    id: alpicool

alpicool_ble:
  ble_client_id: alpicool
  id: fridge

climate:
  - platform: alpicool_ble
    name: "Fridge"

sensor:
  - platform: alpicool_ble
    current_temperature:
      name: "Fridge Temperature"
    target_temperature:
      name: "Fridge Target"
    battery_percent:
      name: "Fridge Battery"
    battery_voltage:
      name: "Fridge Voltage"

switch:
  - platform: alpicool_ble
    power:
      name: "Fridge Power"
    controls_lock:
      name: "Fridge Lock"

select:
  - platform: alpicool_ble
    run_mode:
      name: "Fridge Mode"
    battery_saver:
      name: "Fridge Battery Saver"

binary_sensor:
  - platform: alpicool_ble
    powered_on:
      name: "Fridge Running"
    controls_locked:
      name: "Fridge Locked"
```

## Protocol

See [docs/protocol.md](docs/protocol.md) for the reverse-engineered BLE protocol reference.

## Credits

Protocol decoded from prior work by:
- [klightspeed/BrassMonkeyFridgeMonitor](https://github.com/klightspeed/BrassMonkeyFridgeMonitor)
- [johnelliott/alpicoold](https://github.com/johnelliott/alpicoold)
- [oh2mp/esp32_ble2mqtt](https://github.com/oh2mp/esp32_ble2mqtt)
