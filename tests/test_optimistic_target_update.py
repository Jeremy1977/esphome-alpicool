from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "components"
    / "alpicool_ble"
    / "alpicool_ble.cpp"
)


def test_climate_target_is_published_immediately_after_user_control():
    source = SOURCE.read_text()
    control = source[source.index("void AlpicoolClimate::control"):]
    send = "this->parent_->send_set_target((int8_t) *call.get_target_temperature(), this->zone_);"
    optimistic = "this->target_temperature = *call.get_target_temperature();\n    this->publish_state();"

    assert send in control
    assert optimistic in control
    assert control.index(send) < control.index(optimistic)
