from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "components"
    / "alpicool_ble"
    / "alpicool_ble.cpp"
)


def test_fridge_query_uses_write_without_response():
    """The IceCube rejects a Write Request with GATT status 0x03."""
    source = SOURCE.read_text()
    send_frame = source[source.index("void AlpicoolBle::send_frame_"):]
    assert "ESP_GATT_WRITE_TYPE_NO_RSP" in send_frame
