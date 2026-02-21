"""Pure Python implementation of the Alpicool BLE protocol for testing."""

from dataclasses import dataclass
from typing import Optional
import struct

HEADER = bytes([0xFE, 0xFE])

CMD_BIND = 0x00
CMD_QUERY = 0x01
CMD_SET = 0x02
CMD_VERSION = 0x03
CMD_RESET = 0x04
CMD_SET_UNIT1_TARGET = 0x05
CMD_SET_UNIT2_TARGET = 0x06


@dataclass
class FridgeState:
    controls_locked: bool = False
    powered_on: bool = False
    run_mode: int = 0  # 0=Max, 1=Eco
    battery_saver: int = 0  # 0=Low, 1=Mid, 2=High
    unit1_target_temp: int = 0
    temp_max: int = 20
    temp_min: int = -20
    unit1_hysteresis: int = 2
    start_delay: int = 0
    temp_unit: int = 0  # 0=C, 1=F
    unit1_tc_hot: int = 0
    unit1_tc_mid: int = 0
    unit1_tc_cold: int = 0
    unit1_tc_halt: int = 0
    unit1_current_temp: int = 0
    battery_percent: int = 0
    battery_volt_int: int = 0
    battery_volt_frac: int = 0
    # Dual-zone fields (optional)
    unit2_target_temp: Optional[int] = None
    unit2_hysteresis: Optional[int] = None
    unit2_tc_hot: Optional[int] = None
    unit2_tc_mid: Optional[int] = None
    unit2_tc_cold: Optional[int] = None
    unit2_tc_halt: Optional[int] = None
    unit2_current_temp: Optional[int] = None
    running_status: Optional[int] = None

    @property
    def is_dual_zone(self) -> bool:
        return self.unit2_target_temp is not None

    @property
    def battery_voltage(self) -> float:
        return self.battery_volt_int + self.battery_volt_frac / 10.0

    @property
    def battery_unknown(self) -> bool:
        return self.battery_percent == 0x7F


def checksum(data: bytes) -> int:
    """Calculate 16-bit checksum (sum of all bytes)."""
    return sum(data) & 0xFFFF


def build_frame(cmd: int, payload: bytes = b"") -> bytes:
    """Build a complete frame with header, length, command, payload, and checksum."""
    length = 1 + len(payload) + 2  # cmd + payload + 2-byte checksum
    frame_without_checksum = HEADER + bytes([length, cmd]) + payload
    cs = checksum(frame_without_checksum)
    return frame_without_checksum + struct.pack(">H", cs)


def build_query() -> bytes:
    """Build a query command frame (no payload)."""
    return build_frame(CMD_QUERY)


def build_set_target(temp: int, zone: int = 1) -> bytes:
    """Build a set target temperature command."""
    cmd = CMD_SET_UNIT1_TARGET if zone == 1 else CMD_SET_UNIT2_TARGET
    temp_byte = temp & 0xFF  # signed to unsigned
    return build_frame(cmd, bytes([temp_byte]))


def validate_checksum(frame: bytes) -> bool:
    """Validate frame checksum. Accepts both normal and doubled checksums."""
    if len(frame) < 5:
        return False
    if frame[0:2] != HEADER:
        return False
    cs_received = struct.unpack(">H", frame[-2:])[0]
    cs_calculated = checksum(frame[:-2])
    # Accept both normal and doubled (firmware bug)
    return cs_received == cs_calculated or cs_received == (cs_calculated * 2) & 0xFFFF


def validate_frame(frame: bytes) -> bool:
    """Validate frame structure (header + length) without checking trailing bytes.

    Some firmware (e.g. A1-4X) uses non-standard trailing bytes that encode
    operational state rather than a checksum. This validates only the header
    and that the frame length matches the length field.
    """
    if len(frame) < 5:
        return False
    if frame[0:2] != HEADER:
        return False
    length = frame[2]
    expected_total = 3 + length  # header(2) + length(1) + length bytes
    return len(frame) == expected_total


def build_set(state: "FridgeState") -> bytes:
    """Build a Set (0x02) command frame from current state.

    The Set command sends the first 14 payload fields (controls_locked through
    unit1_tc_halt) to update all settings at once.
    """
    def unsigned(v):
        return v & 0xFF

    payload = bytes([
        int(state.controls_locked),
        int(state.powered_on),
        state.run_mode,
        state.battery_saver,
        unsigned(state.unit1_target_temp),
        unsigned(state.temp_max),
        unsigned(state.temp_min),
        unsigned(state.unit1_hysteresis),
        state.start_delay,
        state.temp_unit,
        unsigned(state.unit1_tc_hot),
        unsigned(state.unit1_tc_mid),
        unsigned(state.unit1_tc_cold),
        unsigned(state.unit1_tc_halt),
    ])
    return build_frame(CMD_SET, payload)


def parse_response(frame: bytes) -> Optional[FridgeState]:
    """Parse a query or set response frame into a FridgeState.

    Both Query (0x01) and Set (0x02) responses use the same 18-byte payload format.
    """
    if len(frame) < 5:
        return None
    if frame[0:2] != HEADER:
        return None

    length = frame[2]
    cmd = frame[3]

    if cmd not in (CMD_QUERY, CMD_SET):
        return None

    # Payload starts at byte 4, ends before 2-byte checksum
    payload = frame[4:-2]

    if len(payload) < 18:
        return None

    def signed(b):
        return b if b < 128 else b - 256

    state = FridgeState(
        controls_locked=bool(payload[0]),
        powered_on=bool(payload[1]),
        run_mode=payload[2],
        battery_saver=payload[3],
        unit1_target_temp=signed(payload[4]),
        temp_max=signed(payload[5]),
        temp_min=signed(payload[6]),
        unit1_hysteresis=signed(payload[7]),
        start_delay=payload[8],
        temp_unit=payload[9],
        unit1_tc_hot=signed(payload[10]),
        unit1_tc_mid=signed(payload[11]),
        unit1_tc_cold=signed(payload[12]),
        unit1_tc_halt=signed(payload[13]),
        unit1_current_temp=signed(payload[14]),
        battery_percent=payload[15],
        battery_volt_int=payload[16],
        battery_volt_frac=payload[17],
    )

    # Dual-zone extension
    if len(payload) >= 28:
        state.unit2_target_temp = signed(payload[18])
        state.unit2_hysteresis = signed(payload[21])
        state.unit2_tc_hot = signed(payload[22])
        state.unit2_tc_mid = signed(payload[23])
        state.unit2_tc_cold = signed(payload[24])
        state.unit2_tc_halt = signed(payload[25])
        state.unit2_current_temp = signed(payload[26])
        state.running_status = payload[27]

    return state


class FrameAssembler:
    """Buffer and reassemble partial BLE frames."""

    def __init__(self):
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        """Feed data and return list of complete frames."""
        self._buffer.extend(data)
        frames = []

        while len(self._buffer) >= 5:
            # Find header
            idx = self._buffer.find(HEADER)
            if idx < 0:
                self._buffer.clear()
                break
            if idx > 0:
                self._buffer = self._buffer[idx:]

            if len(self._buffer) < 3:
                break

            length = self._buffer[2]
            total = 3 + length  # header(2) + length(1) + length bytes

            if len(self._buffer) < total:
                break

            frame = bytes(self._buffer[:total])
            self._buffer = self._buffer[total:]
            frames.append(frame)

        return frames
