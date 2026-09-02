#include "alpicool_ble.h"
#include "esphome/core/log.h"

namespace esphome {
namespace alpicool_ble {

static const char *const TAG = "alpicool_ble";

void AlpicoolBle::setup() {}

void AlpicoolBle::dump_config() {
  ESP_LOGCONFIG(TAG, "Alpicool BLE:");
  ESP_LOGCONFIG(TAG, "  Throttle: %ums", this->throttle_);
  LOG_SENSOR("  ", "Current Temperature", this->current_temp_sensor_);
  LOG_SENSOR("  ", "Target Temperature", this->target_temp_sensor_);
  LOG_SENSOR("  ", "Battery Percent", this->battery_percent_sensor_);
  LOG_SENSOR("  ", "Battery Voltage", this->battery_voltage_sensor_);
  LOG_BINARY_SENSOR("  ", "Powered On", this->powered_on_sensor_);
  LOG_BINARY_SENSOR("  ", "Controls Locked", this->controls_locked_sensor_);
}

void AlpicoolBle::update() {
  if (!this->connected_) return;
  uint32_t now = millis();
  if (now - this->last_query_ >= this->throttle_) {
    this->send_query();
    this->last_query_ = now;
  }
  this->flush_pending_();
}

void AlpicoolBle::gattc_event_handler(esp_gattc_cb_event_t event,
                                       esp_gatt_if_t gattc_if,
                                       esp_ble_gattc_cb_param_t *param) {
  switch (event) {
    case ESP_GATTC_OPEN_EVT: {
      if (param->open.status == ESP_GATT_OK) {
        ESP_LOGI(TAG, "Connected to Alpicool fridge");
      } else {
        ESP_LOGW(TAG, "Connect failed, status=%d", param->open.status);
      }
      break;
    }
    case ESP_GATTC_DISCONNECT_EVT: {
      ESP_LOGI(TAG, "Disconnected");
      this->connected_ = false;
      this->write_handle_ = 0;
      this->notify_handle_ = 0;
      this->rx_buffer_.clear();
      break;
    }
    case ESP_GATTC_SEARCH_CMPL_EVT: {
      auto *write_chr = this->parent_->get_characteristic(SERVICE_UUID, CHAR_WRITE_UUID);
      if (write_chr == nullptr) {
        ESP_LOGW(TAG, "Write characteristic 0x1235 not found");
        break;
      }
      this->write_handle_ = write_chr->handle;

      auto *notify_chr = this->parent_->get_characteristic(SERVICE_UUID, CHAR_NOTIFY_UUID);
      if (notify_chr == nullptr) {
        ESP_LOGW(TAG, "Notify characteristic 0x1236 not found");
        break;
      }
      this->notify_handle_ = notify_chr->handle;

      auto status = esp_ble_gattc_register_for_notify(
          this->parent_->get_gattc_if(), this->parent_->get_remote_bda(), notify_chr->handle);
      if (status != ESP_OK) {
        ESP_LOGW(TAG, "Register notify failed: %d", status);
      }
      ESP_LOGI(TAG, "Service discovery complete, write=0x%x notify=0x%x",
               this->write_handle_, this->notify_handle_);
      break;
    }
    case ESP_GATTC_REG_FOR_NOTIFY_EVT: {
      if (param->reg_for_notify.status == ESP_GATT_OK) {
        ESP_LOGI(TAG, "Notifications registered, sending first query");
        this->connected_ = true;
        this->last_query_ = 0;
        this->send_query();
        this->flush_pending_();
      } else {
        ESP_LOGW(TAG, "Register notify failed: %d", param->reg_for_notify.status);
      }
      break;
    }
    case ESP_GATTC_NOTIFY_EVT: {
      if (param->notify.handle != this->notify_handle_) break;
      this->rx_buffer_.insert(this->rx_buffer_.end(),
                              param->notify.value,
                              param->notify.value + param->notify.value_len);

      while (this->rx_buffer_.size() >= 5) {
        size_t idx = 0;
        bool found = false;
        for (size_t i = 0; i + 1 < this->rx_buffer_.size(); i++) {
          if (this->rx_buffer_[i] == HEADER_BYTE && this->rx_buffer_[i + 1] == HEADER_BYTE) {
            idx = i;
            found = true;
            break;
          }
        }
        if (!found) {
          this->rx_buffer_.clear();
          break;
        }
        if (idx > 0) {
          this->rx_buffer_.erase(this->rx_buffer_.begin(), this->rx_buffer_.begin() + idx);
        }
        if (this->rx_buffer_.size() < 3) break;

        uint8_t length = this->rx_buffer_[2];
        size_t total = 3 + length;
        if (this->rx_buffer_.size() < total) break;

        this->on_frame_(this->rx_buffer_.data(), total);
        this->rx_buffer_.erase(this->rx_buffer_.begin(), this->rx_buffer_.begin() + total);
      }
      break;
    }
    default:
      break;
  }
}

void AlpicoolBle::on_frame_(const uint8_t *data, size_t length) {
  if (length < 5) return;
  uint8_t cmd = data[3];
  const uint8_t *payload = data + 4;
  size_t payload_len = length - 6;

  ESP_LOGD(TAG, "Frame: cmd=0x%02x payload_len=%d", cmd, payload_len);

  if ((cmd == CMD_QUERY || cmd == CMD_SET) && payload_len >= 18) {
    this->parse_state_payload_(payload, payload_len);
    this->publish_state_();
  } else if (cmd == CMD_SET_UNIT1_TARGET && payload_len >= 1) {
    ESP_LOGD(TAG, "SetTarget ACK: temp=%d", (int8_t) payload[0]);
  }
}

void AlpicoolBle::parse_state_payload_(const uint8_t *p, size_t len) {
  this->state_.controls_locked = p[0] != 0;
  this->state_.powered_on = p[1] != 0;
  this->state_.run_mode = p[2];
  this->state_.battery_saver = p[3];
  this->state_.target_temp = (int8_t) p[4];
  this->state_.temp_max = (int8_t) p[5];
  this->state_.temp_min = (int8_t) p[6];
  this->state_.hysteresis = (int8_t) p[7];
  this->state_.start_delay = p[8];
  this->state_.temp_unit = p[9];
  this->state_.tc_hot = (int8_t) p[10];
  this->state_.tc_mid = (int8_t) p[11];
  this->state_.tc_cold = (int8_t) p[12];
  this->state_.tc_halt = (int8_t) p[13];
  this->state_.current_temp = (int8_t) p[14];
  this->state_.battery_percent = p[15];
  this->state_.battery_volt_int = p[16];
  this->state_.battery_volt_frac = p[17];
  this->state_.dual_zone = len >= 28;
  if (this->state_.dual_zone) {
    this->state_.unit2_target_temp = static_cast<int8_t>(p[18]);
    this->state_.unit2_hysteresis = static_cast<int8_t>(p[21]);
    this->state_.unit2_tc_hot = static_cast<int8_t>(p[22]);
    this->state_.unit2_tc_mid = static_cast<int8_t>(p[23]);
    this->state_.unit2_tc_cold = static_cast<int8_t>(p[24]);
    this->state_.unit2_tc_halt = static_cast<int8_t>(p[25]);
    this->state_.unit2_current_temp = static_cast<int8_t>(p[26]);
    this->state_.running_status = p[27];
  }
  this->state_.valid = true;
}

void AlpicoolBle::publish_state_() {
  if (!this->state_.valid) return;

  if (this->current_temp_sensor_ != nullptr)
    this->current_temp_sensor_->publish_state(this->state_.current_temp);
  if (this->target_temp_sensor_ != nullptr)
    this->target_temp_sensor_->publish_state(this->state_.target_temp);
  if (this->battery_percent_sensor_ != nullptr) {
    if (this->state_.battery_percent == 0x7F) {
      this->battery_percent_sensor_->publish_state(NAN);
    } else {
      this->battery_percent_sensor_->publish_state(this->state_.battery_percent);
    }
  }
  if (this->battery_voltage_sensor_ != nullptr) {
    float voltage = this->state_.battery_volt_int + this->state_.battery_volt_frac / 10.0f;
    this->battery_voltage_sensor_->publish_state(voltage);
  }
  if (this->state_.dual_zone) {
    if (this->zone2_current_temp_sensor_ != nullptr)
      this->zone2_current_temp_sensor_->publish_state(this->state_.unit2_current_temp);
    if (this->zone2_target_temp_sensor_ != nullptr)
      this->zone2_target_temp_sensor_->publish_state(this->state_.unit2_target_temp);
  }
  if (this->powered_on_sensor_ != nullptr)
    this->powered_on_sensor_->publish_state(this->state_.powered_on);
  if (this->controls_locked_sensor_ != nullptr)
    this->controls_locked_sensor_->publish_state(this->state_.controls_locked);
  if (this->power_switch_ != nullptr)
    ((switch_::Switch *) this->power_switch_)->publish_state(this->state_.powered_on);
  if (this->controls_lock_switch_ != nullptr)
    ((switch_::Switch *) this->controls_lock_switch_)->publish_state(this->state_.controls_locked);

  // Update climate
  if (this->climate_ != nullptr) {
    this->climate_->update_from_state(this->state_);
  }
  if (this->zone2_climate_ != nullptr && this->state_.dual_zone) {
    this->zone2_climate_->update_from_state(this->state_);
  }

  // Update selects
  if (this->run_mode_select_ != nullptr) {
    if (this->state_.run_mode == 0)
      this->run_mode_select_->publish_state("Max");
    else
      this->run_mode_select_->publish_state("Eco");
  }
  if (this->battery_saver_select_ != nullptr) {
    switch (this->state_.battery_saver) {
      case 0: this->battery_saver_select_->publish_state("Low"); break;
      case 1: this->battery_saver_select_->publish_state("Mid"); break;
      case 2: this->battery_saver_select_->publish_state("High"); break;
      default: this->battery_saver_select_->publish_state("Low"); break;
    }
  }
}

void AlpicoolBle::send_frame_(uint8_t cmd, const uint8_t *payload, size_t payload_len) {
  if (!this->connected_ || this->write_handle_ == 0) {
    ESP_LOGW(TAG, "Cannot send: not connected");
    return;
  }

  size_t length_field = 1 + payload_len + 2;
  std::vector<uint8_t> frame;
  frame.reserve(3 + length_field);
  frame.push_back(HEADER_BYTE);
  frame.push_back(HEADER_BYTE);
  frame.push_back(length_field);
  frame.push_back(cmd);
  if (payload_len > 0) {
    frame.insert(frame.end(), payload, payload + payload_len);
  }

  uint16_t cs = 0;
  for (uint8_t b : frame) cs += b;
  frame.push_back((cs >> 8) & 0xFF);
  frame.push_back(cs & 0xFF);

  auto status = esp_ble_gattc_write_char(
      this->parent_->get_gattc_if(), this->parent_->get_conn_id(),
      this->write_handle_, frame.size(), frame.data(),
      ESP_GATT_WRITE_TYPE_RSP, ESP_GATT_AUTH_REQ_NONE);

  if (status != ESP_OK) {
    ESP_LOGW(TAG, "Write failed: %d", status);
    this->pending_retries_++;
  } else {
    ESP_LOGD(TAG, "Sent cmd=0x%02x len=%d", cmd, frame.size());
  }
}

void AlpicoolBle::send_query() {
  this->send_frame_(CMD_QUERY, nullptr, 0);
}

void AlpicoolBle::send_set_target(int8_t temp, uint8_t zone) {
  uint8_t payload[] = {static_cast<uint8_t>(temp)};
  this->send_frame_(zone == 2 ? CMD_SET_UNIT2_TARGET : CMD_SET_UNIT1_TARGET, payload, 1);
}

void AlpicoolBle::send_settings(FridgeState desired) {
  this->enqueue_desired_(desired);
}

void AlpicoolBle::enqueue_desired_(FridgeState desired) {
  if (!this->pending_desired_.has_value()) {
    this->pending_queued_at_ = millis();
    this->pending_retries_ = 0;
  }
  this->pending_desired_ = desired;
  if (this->connected_) {
    this->flush_pending_();
  }
}

void AlpicoolBle::flush_pending_() {
  if (!this->pending_desired_.has_value()) return;
  if (!this->connected_ || this->write_handle_ == 0) return;

  uint32_t now = millis();
  if (now - this->pending_queued_at_ > CMD_TIMEOUT_MS) {
    ESP_LOGW(TAG, "Pending command expired after %ums", now - this->pending_queued_at_);
    this->pending_desired_.reset();
    return;
  }
  if (this->pending_retries_ >= CMD_MAX_RETRIES) {
    ESP_LOGW(TAG, "Pending command dropped after %d retries", this->pending_retries_);
    this->pending_desired_.reset();
    return;
  }

  FridgeState &desired = *this->pending_desired_;

  // Use fast CMD_SET_UNIT1_TARGET when only target_temp differs
  bool target_only = (desired.target_temp != this->state_.target_temp) &&
                     (desired.controls_locked == this->state_.controls_locked) &&
                     (desired.powered_on == this->state_.powered_on) &&
                     (desired.run_mode == this->state_.run_mode) &&
                     (desired.battery_saver == this->state_.battery_saver) &&
                     (desired.temp_max == this->state_.temp_max) &&
                     (desired.temp_min == this->state_.temp_min) &&
                     (desired.hysteresis == this->state_.hysteresis) &&
                     (desired.start_delay == this->state_.start_delay) &&
                     (desired.temp_unit == this->state_.temp_unit) &&
                     (desired.tc_hot == this->state_.tc_hot) &&
                     (desired.tc_mid == this->state_.tc_mid) &&
                     (desired.tc_cold == this->state_.tc_cold) &&
                     (desired.tc_halt == this->state_.tc_halt);

  if (target_only) {
    uint8_t payload[] = {(uint8_t) desired.target_temp};
    this->send_frame_(CMD_SET_UNIT1_TARGET, payload, 1);
  } else {
    uint8_t payload[14];
    payload[0] = desired.controls_locked ? 1 : 0;
    payload[1] = desired.powered_on ? 1 : 0;
    payload[2] = desired.run_mode;
    payload[3] = desired.battery_saver;
    payload[4] = (uint8_t) desired.target_temp;
    payload[5] = (uint8_t) desired.temp_max;
    payload[6] = (uint8_t) desired.temp_min;
    payload[7] = (uint8_t) desired.hysteresis;
    payload[8] = desired.start_delay;
    payload[9] = desired.temp_unit;
    payload[10] = (uint8_t) desired.tc_hot;
    payload[11] = (uint8_t) desired.tc_mid;
    payload[12] = (uint8_t) desired.tc_cold;
    payload[13] = (uint8_t) desired.tc_halt;
    this->send_frame_(CMD_SET, payload, 14);
  }

  this->pending_desired_.reset();
}

// --- Switch ---

void AlpicoolBleSwitch::write_state(bool state) {
  if (this->parent_ == nullptr) return;
  FridgeState desired = this->parent_->get_state();
  if (this->is_power_) {
    desired.powered_on = state;
  } else {
    desired.controls_locked = state;
  }
  this->parent_->send_settings(desired);
}

// --- Select ---

void AlpicoolBleSelect::control(const std::string &value) {
  if (this->parent_ == nullptr) return;
  FridgeState desired = this->parent_->get_state();
  if (this->type_ == 0) {
    // run_mode
    if (value == "Max") desired.run_mode = 0;
    else if (value == "Eco") desired.run_mode = 1;
  } else if (this->type_ == 1) {
    // battery_saver
    if (value == "Low") desired.battery_saver = 0;
    else if (value == "Mid") desired.battery_saver = 1;
    else if (value == "High") desired.battery_saver = 2;
  }
  this->parent_->send_settings(desired);
}

// --- Climate ---

climate::ClimateTraits AlpicoolClimate::traits() {
  auto traits = climate::ClimateTraits();
  traits.add_supported_mode(climate::CLIMATE_MODE_OFF);
  traits.add_supported_mode(climate::CLIMATE_MODE_COOL);
  traits.set_supported_custom_presets({"Max", "Eco"});
  traits.set_visual_min_temperature(-20);
  traits.set_visual_max_temperature(20);
  traits.set_visual_temperature_step(1);
  return traits;
}

void AlpicoolClimate::update_from_state(const FridgeState &state) {
  if (this->zone_ == 2) {
    if (!state.dual_zone) return;
    this->current_temperature = state.unit2_current_temp;
    this->target_temperature = state.unit2_target_temp;
  } else {
    this->current_temperature = state.current_temp;
    this->target_temperature = state.target_temp;
  }
  this->mode = state.powered_on ? climate::CLIMATE_MODE_COOL : climate::CLIMATE_MODE_OFF;
  this->set_custom_preset_(state.run_mode == 0 ? "Max" : "Eco");
  this->publish_state();
}

void AlpicoolClimate::control(const climate::ClimateCall &call) {
  if (this->parent_ == nullptr) return;

  if (call.get_target_temperature().has_value()) {
    this->parent_->send_set_target((int8_t) *call.get_target_temperature(), this->zone_);
  }

  // Power and Eco/Max are shared appliance settings, so they are owned by Zone 1.
  if (this->zone_ == 2) return;
  FridgeState desired = this->parent_->get_state();
  if (call.get_mode().has_value()) {
    desired.powered_on = (*call.get_mode() != climate::CLIMATE_MODE_OFF);
  }
  auto custom_preset = call.get_custom_preset();
  if (!custom_preset.empty()) {
    auto preset = custom_preset;
    if (preset == "Max") desired.run_mode = 0;
    else if (preset == "Eco") desired.run_mode = 1;
  }
  if (call.get_mode().has_value() || !custom_preset.empty()) {
    this->parent_->send_settings(desired);
  }
}

}  // namespace alpicool_ble
}  // namespace esphome
