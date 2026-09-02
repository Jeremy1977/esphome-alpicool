from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "components"
    / "alpicool_ble"
    / "alpicool_ble.cpp"
)


def test_logs_gatt_write_results_and_all_notification_handles():
    """A silent fridge needs transport-level evidence before protocol changes."""
    source = SOURCE.read_text()
    assert "ESP_GATTC_WRITE_CHAR_EVT" in source
    assert "Query write acknowledged" in source
    assert "Notify: handle=0x%x len=%d" in source
