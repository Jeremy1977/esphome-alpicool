from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "components"
    / "alpicool_ble"
    / "alpicool_ble.cpp"
)


def test_notification_subscription_writes_cccd_before_marking_connected():
    """BLE notifications require a CCCD write after registration."""
    source = SOURCE.read_text()
    cccd = source.index("ESP_GATT_UUID_CHAR_CLIENT_CONFIG")
    cccd_write = source.index("esp_ble_gattc_write_char_descr", cccd)
    connected = source.index("this->connected_ = true", cccd)
    assert cccd_write < connected
