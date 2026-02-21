#pragma once

#include "esphome/core/component.h"
#include "esphome/components/ble_client/ble_client.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/climate/climate.h"
#include "esphome/components/select/select.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/switch/switch.h"
#include <vector>

namespace esphome {
namespace alpicool_ble {

static const uint16_t SERVICE_UUID = 0x1234;
static const uint16_t CHAR_WRITE_UUID = 0x1235;
static const uint16_t CHAR_NOTIFY_UUID = 0x1236;

static const uint8_t CMD_QUERY = 0x01;
static const uint8_t CMD_SET = 0x02;
static const uint8_t CMD_SET_UNIT1_TARGET = 0x05;
static const uint8_t CMD_SET_UNIT2_TARGET = 0x06;

static const uint8_t HEADER_BYTE = 0xFE;

struct FridgeState {
  bool controls_locked{false};
  bool powered_on{false};
  uint8_t run_mode{0};       // 0=Max, 1=Eco
  uint8_t battery_saver{0};  // 0=Low, 1=Mid, 2=High
  int8_t target_temp{0};
  int8_t temp_max{20};
  int8_t temp_min{-20};
  int8_t hysteresis{2};
  uint8_t start_delay{0};
  uint8_t temp_unit{0};      // 0=C, 1=F
  int8_t tc_hot{0};
  int8_t tc_mid{0};
  int8_t tc_cold{0};
  int8_t tc_halt{0};
  int8_t current_temp{0};
  uint8_t battery_percent{0};
  uint8_t battery_volt_int{0};
  uint8_t battery_volt_frac{0};
  bool valid{false};
};

// Forward declarations
class AlpicoolBleSwitch;
class AlpicoolBleSelect;
class AlpicoolClimate;

class AlpicoolBle : public PollingComponent, public ble_client::BLEClientNode {
 public:
  void setup() override;
  void update() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  void gattc_event_handler(esp_gattc_cb_event_t event, esp_gatt_if_t gattc_if,
                           esp_ble_gattc_cb_param_t *param) override;

  void set_throttle(uint32_t throttle) { this->throttle_ = throttle; }

  // Sensors
  void set_current_temperature_sensor(sensor::Sensor *s) { this->current_temp_sensor_ = s; }
  void set_target_temperature_sensor(sensor::Sensor *s) { this->target_temp_sensor_ = s; }
  void set_battery_percent_sensor(sensor::Sensor *s) { this->battery_percent_sensor_ = s; }
  void set_battery_voltage_sensor(sensor::Sensor *s) { this->battery_voltage_sensor_ = s; }

  // Binary sensors
  void set_powered_on_binary_sensor(binary_sensor::BinarySensor *s) { this->powered_on_sensor_ = s; }
  void set_controls_locked_binary_sensor(binary_sensor::BinarySensor *s) { this->controls_locked_sensor_ = s; }

  // Switches
  void set_power_switch(AlpicoolBleSwitch *s) { this->power_switch_ = s; }
  void set_controls_lock_switch(AlpicoolBleSwitch *s) { this->controls_lock_switch_ = s; }

  // Climate
  void set_climate(AlpicoolClimate *c) { this->climate_ = c; }

  // Selects
  void set_run_mode_select(AlpicoolBleSelect *s) { this->run_mode_select_ = s; }
  void set_battery_saver_select(AlpicoolBleSelect *s) { this->battery_saver_select_ = s; }

  // Actions
  void send_query();
  void send_set_target(int8_t temp);
  void send_settings(FridgeState desired);

  const FridgeState &get_state() const { return this->state_; }
  bool is_connected() const { return this->connected_; }

 protected:
  void on_frame_(const uint8_t *data, size_t length);
  void parse_state_payload_(const uint8_t *payload, size_t length);
  void publish_state_();
  void send_frame_(uint8_t cmd, const uint8_t *payload, size_t payload_len);

  uint16_t write_handle_{0};
  uint16_t notify_handle_{0};
  uint32_t throttle_{10000};
  uint32_t last_query_{0};
  bool connected_{false};

  std::vector<uint8_t> rx_buffer_;
  FridgeState state_;

  // Sensors
  sensor::Sensor *current_temp_sensor_{nullptr};
  sensor::Sensor *target_temp_sensor_{nullptr};
  sensor::Sensor *battery_percent_sensor_{nullptr};
  sensor::Sensor *battery_voltage_sensor_{nullptr};

  // Binary sensors
  binary_sensor::BinarySensor *powered_on_sensor_{nullptr};
  binary_sensor::BinarySensor *controls_locked_sensor_{nullptr};

  // Switches
  AlpicoolBleSwitch *power_switch_{nullptr};
  AlpicoolBleSwitch *controls_lock_switch_{nullptr};

  // Climate
  AlpicoolClimate *climate_{nullptr};

  // Selects
  AlpicoolBleSelect *run_mode_select_{nullptr};
  AlpicoolBleSelect *battery_saver_select_{nullptr};
};

// Switch for power and controls lock
class AlpicoolBleSwitch : public switch_::Switch, public Component {
 public:
  void set_parent(AlpicoolBle *parent) { this->parent_ = parent; }
  void set_is_power(bool is_power) { this->is_power_ = is_power; }
  void write_state(bool state) override;

 protected:
  AlpicoolBle *parent_{nullptr};
  bool is_power_{true};
};

// Select for run_mode and battery_saver
class AlpicoolBleSelect : public select::Select, public Component {
 public:
  void set_parent(AlpicoolBle *parent) { this->parent_ = parent; }
  void set_select_type(uint8_t type) { this->type_ = type; }  // 0=run_mode, 1=battery_saver
  void control(const std::string &value) override;

 protected:
  AlpicoolBle *parent_{nullptr};
  uint8_t type_{0};
};

// Climate entity for fridge thermostat control
class AlpicoolClimate : public climate::Climate, public Component {
 public:
  void set_parent(AlpicoolBle *parent) { this->parent_ = parent; }

  climate::ClimateTraits traits() override;
  void control(const climate::ClimateCall &call) override;

  void update_from_state(const FridgeState &state);

 protected:
  AlpicoolBle *parent_{nullptr};
};

}  // namespace alpicool_ble
}  // namespace esphome
