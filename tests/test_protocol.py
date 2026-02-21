"""Tests for Alpicool BLE protocol parser."""

import pytest
from alpicool_protocol import (
    FridgeState,
    FrameAssembler,
    build_frame,
    build_query,
    build_set,
    build_set_target,
    checksum,
    parse_response,
    validate_checksum,
    validate_frame,
    CMD_QUERY,
    CMD_SET,
    CMD_SET_UNIT1_TARGET,
)


# -- Test vectors from protocol docs and live capture --

# Known query command
QUERY_CMD = bytes.fromhex("FE FE 03 01 02 00".replace(" ", ""))

# Doc example: single-zone, -15C target, -13C current, 12.3V, 100%
DOC_RESPONSE = bytes.fromhex(
    "FE FE 15 01 00 01 00 00 F1 14 EC 02 00 00 00 00 00 00 F3 64 0C 03 05 6C"
)

# Live capture from user's fridge (A1-4X, single-zone)
# target=3C, current=4C, 13.9V, 100%, Max mode, tc_cold=-3
LIVE_RESPONSE_1 = bytes.fromhex(
    "FE FE 15 01 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 11 00"
)

# -- Live BLE capture session vectors (2026-02-22) --
# These have non-standard trailing bytes (NOT checksums)

# Query response while compressor running
CAPTURE_QUERY_1 = bytes.fromhex(
    "FEFE 1501 0001 0000 0314 EC02 0000 0000 FD00 0464 0D09 1354".replace(" ", "")
)
# Same query, different trailing bytes (varies per packet)
CAPTURE_QUERY_2 = bytes.fromhex(
    "FEFE 1501 0001 0000 0314 EC02 0000 0000 FD00 0464 0D09 137F".replace(" ", "")
)
# After target changed to 4C
CAPTURE_QUERY_TARGET4 = bytes.fromhex(
    "FEFE 1501 0001 0000 0414 EC02 0000 0000 FD00 0464 0D09 1282".replace(" ", "")
)
# Eco mode enabled
CAPTURE_QUERY_ECO = bytes.fromhex(
    "FEFE 1501 0001 0100 0314 EC02 0000 0000 FD00 0464 0D09 1413".replace(" ", "")
)
# Powered off
CAPTURE_QUERY_OFF = bytes.fromhex(
    "FEFE 1501 0000 0000 0314 EC02 0000 0000 FD00 0464 0D09 091E".replace(" ", "")
)
# Set response (cmd=0x02, echoes full state)
CAPTURE_SET_RESPONSE = bytes.fromhex(
    "FEFE 1502 0001 0000 0314 EC02 0000 0000 FD00 0464 0D09 13BA".replace(" ", "")
)
# SetUnit1Target(4C) response (cmd=0x05, compact ACK)
CAPTURE_SET_TARGET_ACK = bytes.fromhex(
    "FEFE 0405 0413 B3".replace(" ", "")
)
# Version/info response (cmd=0x03)
CAPTURE_VERSION = bytes.fromhex(
    "FEFE 0703 0104 0404 1376".replace(" ", "")
)


class TestChecksum:
    def test_query_checksum(self):
        # Query: FE FE 03 01 02 -> sum = FE+FE+03+01+02 = 0x0202
        # But stored checksum is 00 -> let's check
        frame = QUERY_CMD
        assert frame == build_query()

    def test_checksum_calculation(self):
        data = bytes([0xFE, 0xFE, 0x03, 0x01, 0x02])
        cs = checksum(data)
        assert cs == 0xFE + 0xFE + 0x03 + 0x01 + 0x02

    def test_empty_checksum(self):
        assert checksum(b"") == 0

    def test_overflow_wraps_16bit(self):
        data = bytes([0xFF] * 300)
        cs = checksum(data)
        assert 0 <= cs <= 0xFFFF


class TestValidateChecksum:
    def test_valid_query(self):
        assert validate_checksum(build_query())

    def test_valid_set_target(self):
        assert validate_checksum(build_set_target(-18))

    def test_too_short(self):
        assert not validate_checksum(b"\xFE\xFE\x01")
        assert not validate_checksum(b"")

    def test_wrong_header(self):
        assert not validate_checksum(b"\xAA\xBB\x03\x01\x02\x00")

    def test_wrong_checksum(self):
        frame = bytearray(build_query())
        frame[-1] ^= 0xFF  # corrupt checksum
        assert not validate_checksum(bytes(frame))

    def test_doubled_checksum_accepted(self):
        """Firmware bug: some devices send checksum * 2."""
        frame = bytearray(build_query())
        cs = checksum(frame[:-2])
        doubled = (cs * 2) & 0xFFFF
        frame[-2] = (doubled >> 8) & 0xFF
        frame[-1] = doubled & 0xFF
        assert validate_checksum(bytes(frame))


class TestBuildQuery:
    def test_query_format(self):
        q = build_query()
        assert q[0:2] == b"\xFE\xFE"
        assert q[3] == CMD_QUERY

    def test_query_matches_known(self):
        assert build_query() == QUERY_CMD


class TestBuildSetTarget:
    def test_positive_temp(self):
        frame = build_set_target(5)
        assert frame[3] == CMD_SET_UNIT1_TARGET
        assert frame[4] == 5

    def test_negative_temp(self):
        frame = build_set_target(-18)
        assert frame[3] == CMD_SET_UNIT1_TARGET
        assert frame[4] == 0xEE  # -18 as unsigned byte

    def test_zero_temp(self):
        frame = build_set_target(0)
        assert frame[4] == 0

    def test_zone2(self):
        frame = build_set_target(5, zone=2)
        assert frame[3] == 0x06  # CMD_SET_UNIT2_TARGET

    def test_checksum_valid(self):
        assert validate_checksum(build_set_target(-18))
        assert validate_checksum(build_set_target(20))
        assert validate_checksum(build_set_target(-25, zone=2))


class TestParseResponse:
    def test_doc_example(self):
        state = parse_response(DOC_RESPONSE)
        assert state is not None
        assert state.controls_locked is False
        assert state.powered_on is True
        assert state.run_mode == 0  # Max
        assert state.battery_saver == 0  # Low
        assert state.unit1_target_temp == -15
        assert state.temp_max == 20
        assert state.temp_min == -20
        assert state.unit1_hysteresis == 2
        assert state.start_delay == 0
        assert state.temp_unit == 0  # Celsius
        assert state.unit1_current_temp == -13
        assert state.battery_percent == 100
        assert state.battery_volt_int == 12
        assert state.battery_volt_frac == 3
        assert state.battery_voltage == 12.3
        assert not state.is_dual_zone

    def test_live_capture(self):
        state = parse_response(LIVE_RESPONSE_1)
        assert state is not None
        assert state.powered_on is True
        assert state.run_mode == 0  # Max
        assert state.unit1_target_temp == 3
        assert state.temp_max == 20
        assert state.temp_min == -20
        assert state.unit1_tc_cold == -3
        assert state.unit1_current_temp == 4
        assert state.battery_percent == 100
        assert state.battery_volt_int == 13
        assert state.battery_volt_frac == 9
        assert state.battery_voltage == 13.9

    def test_too_short(self):
        assert parse_response(b"") is None
        assert parse_response(b"\xFE\xFE\x03") is None

    def test_wrong_header(self):
        frame = bytearray(DOC_RESPONSE)
        frame[0] = 0xAA
        assert parse_response(bytes(frame)) is None

    def test_wrong_command(self):
        frame = bytearray(DOC_RESPONSE)
        frame[3] = 0x03  # Version command, not query/set
        assert parse_response(bytes(frame)) is None

    def test_payload_too_short_for_single_zone(self):
        # Header + length + cmd + only 10 bytes payload + checksum
        short = b"\xFE\xFE\x0D\x01" + bytes(10) + b"\x00\x00"
        assert parse_response(short) is None

    def test_signed_temp_boundary(self):
        """Test int8 boundary: 0x80 = -128, 0x7F = 127."""
        frame = bytearray(DOC_RESPONSE)
        # Set current temp to 0x80 (-128)
        frame[4 + 14] = 0x80
        state = parse_response(bytes(frame))
        assert state is not None
        assert state.unit1_current_temp == -128

        # Set current temp to 0x7F (127)
        frame[4 + 14] = 0x7F
        state = parse_response(bytes(frame))
        assert state.unit1_current_temp == 127

    def test_battery_unknown(self):
        """0x7F battery percent means no battery monitoring."""
        frame = bytearray(DOC_RESPONSE)
        frame[4 + 15] = 0x7F
        state = parse_response(bytes(frame))
        assert state is not None
        assert state.battery_unknown is True

    def test_eco_mode(self):
        frame = bytearray(DOC_RESPONSE)
        frame[4 + 2] = 1  # Eco mode
        state = parse_response(bytes(frame))
        assert state.run_mode == 1

    def test_fahrenheit(self):
        frame = bytearray(DOC_RESPONSE)
        frame[4 + 9] = 1  # Fahrenheit
        state = parse_response(bytes(frame))
        assert state.temp_unit == 1

    def test_controls_locked(self):
        frame = bytearray(DOC_RESPONSE)
        frame[4 + 0] = 1
        state = parse_response(bytes(frame))
        assert state.controls_locked is True

    def test_powered_off(self):
        frame = bytearray(DOC_RESPONSE)
        frame[4 + 1] = 0
        state = parse_response(bytes(frame))
        assert state.powered_on is False


class TestDualZone:
    def test_dual_zone_detection(self):
        # Build a dual-zone response (28+ payload bytes)
        payload = bytes(28)
        frame = b"\xFE\xFE" + bytes([1 + 28 + 2, CMD_QUERY]) + payload + b"\x00\x00"
        state = parse_response(frame)
        assert state is not None
        assert state.is_dual_zone

    def test_single_zone_detection(self):
        state = parse_response(DOC_RESPONSE)
        assert state is not None
        assert not state.is_dual_zone
        assert state.unit2_target_temp is None


class TestFrameAssembler:
    def test_complete_frame(self):
        asm = FrameAssembler()
        frames = asm.feed(QUERY_CMD)
        assert len(frames) == 1
        assert frames[0] == QUERY_CMD

    def test_split_frame(self):
        """Frame arrives in two BLE packets."""
        asm = FrameAssembler()
        mid = len(DOC_RESPONSE) // 2
        frames = asm.feed(DOC_RESPONSE[:mid])
        assert len(frames) == 0
        frames = asm.feed(DOC_RESPONSE[mid:])
        assert len(frames) == 1
        assert frames[0] == DOC_RESPONSE

    def test_split_at_every_byte(self):
        """Frame arrives one byte at a time."""
        asm = FrameAssembler()
        for i in range(len(DOC_RESPONSE) - 1):
            frames = asm.feed(DOC_RESPONSE[i : i + 1])
            assert len(frames) == 0
        frames = asm.feed(DOC_RESPONSE[-1:])
        assert len(frames) == 1

    def test_multiple_frames(self):
        """Two frames arrive in one BLE packet."""
        asm = FrameAssembler()
        frames = asm.feed(QUERY_CMD + DOC_RESPONSE)
        assert len(frames) == 2

    def test_garbage_before_header(self):
        """Garbage bytes before valid frame."""
        asm = FrameAssembler()
        frames = asm.feed(b"\x00\x01\x02" + QUERY_CMD)
        assert len(frames) == 1
        assert frames[0] == QUERY_CMD

    def test_empty_feed(self):
        asm = FrameAssembler()
        frames = asm.feed(b"")
        assert len(frames) == 0

    def test_partial_header(self):
        asm = FrameAssembler()
        frames = asm.feed(b"\xFE")
        assert len(frames) == 0
        frames = asm.feed(b"\xFE\x03\x01\x02\x00")
        assert len(frames) == 1

    def test_ble_mtu_fragmentation(self):
        """Real BLE: 24-byte response arrives as 20+4 due to ATT MTU 23."""
        asm = FrameAssembler()
        frames = asm.feed(CAPTURE_QUERY_1[:20])
        assert len(frames) == 0
        frames = asm.feed(CAPTURE_QUERY_1[20:])
        assert len(frames) == 1
        assert frames[0] == CAPTURE_QUERY_1


class TestValidateFrame:
    def test_valid_query(self):
        assert validate_frame(build_query())

    def test_valid_live_capture(self):
        """Live capture packets have non-standard trailing bytes."""
        assert validate_frame(CAPTURE_QUERY_1)
        assert validate_frame(CAPTURE_QUERY_2)
        assert validate_frame(CAPTURE_QUERY_OFF)

    def test_valid_set_response(self):
        assert validate_frame(CAPTURE_SET_RESPONSE)

    def test_valid_set_target_ack(self):
        assert validate_frame(CAPTURE_SET_TARGET_ACK)

    def test_valid_version(self):
        assert validate_frame(CAPTURE_VERSION)

    def test_too_short(self):
        assert not validate_frame(b"\xFE\xFE\x01")
        assert not validate_frame(b"")

    def test_wrong_header(self):
        assert not validate_frame(b"\xAA\xBB\x03\x01\x02\x00")

    def test_length_mismatch(self):
        """Frame claiming more data than present."""
        frame = b"\xFE\xFE\xFF\x01\x00\x00"  # length=255 but only 3 bytes follow
        assert not validate_frame(frame)


class TestLiveCapture:
    """Tests against real BLE capture from A1-4X fridge (2026-02-22)."""

    def test_query_on_compressor_running(self):
        state = parse_response(CAPTURE_QUERY_1)
        assert state is not None
        assert state.powered_on is True
        assert state.run_mode == 0  # Max
        assert state.unit1_target_temp == 3
        assert state.unit1_current_temp == 4
        assert state.unit1_tc_cold == -3
        assert state.battery_voltage == 13.9
        assert state.battery_percent == 100
        assert not state.is_dual_zone

    def test_varying_trailing_bytes_same_state(self):
        """Different trailing bytes should parse to same state."""
        s1 = parse_response(CAPTURE_QUERY_1)
        s2 = parse_response(CAPTURE_QUERY_2)
        assert s1 is not None and s2 is not None
        assert s1.unit1_target_temp == s2.unit1_target_temp
        assert s1.unit1_current_temp == s2.unit1_current_temp
        assert s1.powered_on == s2.powered_on
        assert s1.battery_voltage == s2.battery_voltage

    def test_target_temp_changed(self):
        state = parse_response(CAPTURE_QUERY_TARGET4)
        assert state is not None
        assert state.unit1_target_temp == 4

    def test_eco_mode(self):
        state = parse_response(CAPTURE_QUERY_ECO)
        assert state is not None
        assert state.run_mode == 1  # Eco

    def test_powered_off(self):
        state = parse_response(CAPTURE_QUERY_OFF)
        assert state is not None
        assert state.powered_on is False

    def test_set_response_parses(self):
        """Set (0x02) response has same payload format as Query."""
        state = parse_response(CAPTURE_SET_RESPONSE)
        assert state is not None
        assert state.powered_on is True
        assert state.unit1_target_temp == 3

    def test_non_standard_trailing_bytes_fail_checksum(self):
        """Live capture trailing bytes are NOT standard checksums."""
        assert not validate_checksum(CAPTURE_QUERY_1)
        assert not validate_checksum(CAPTURE_QUERY_2)

    def test_non_standard_trailing_bytes_pass_frame(self):
        """But they pass structural validation."""
        assert validate_frame(CAPTURE_QUERY_1)
        assert validate_frame(CAPTURE_QUERY_2)


class TestBuildSet:
    def test_build_set_default_state(self):
        state = FridgeState()
        frame = build_set(state)
        assert frame[3] == CMD_SET
        assert validate_checksum(frame)

    def test_build_set_payload_fields(self):
        state = FridgeState(
            controls_locked=False,
            powered_on=True,
            run_mode=0,
            battery_saver=0,
            unit1_target_temp=3,
            temp_max=20,
            temp_min=-20,
            unit1_hysteresis=2,
            start_delay=0,
            temp_unit=0,
            unit1_tc_hot=0,
            unit1_tc_mid=0,
            unit1_tc_cold=-3,
            unit1_tc_halt=0,
        )
        frame = build_set(state)
        # Payload starts at byte 4
        assert frame[4] == 0  # controls_locked
        assert frame[5] == 1  # powered_on
        assert frame[6] == 0  # run_mode
        assert frame[8] == 3  # target_temp
        assert frame[10] == 0xEC  # temp_min = -20 as unsigned
        assert frame[16] == 0xFD  # tc_cold = -3 as unsigned

    def test_build_set_eco_mode(self):
        state = FridgeState(powered_on=True, run_mode=1)
        frame = build_set(state)
        assert frame[6] == 1  # run_mode = Eco

    def test_build_set_battery_saver_levels(self):
        for level in (0, 1, 2):
            state = FridgeState(powered_on=True, battery_saver=level)
            frame = build_set(state)
            assert frame[7] == level  # battery_saver at payload[3]
            assert validate_checksum(frame)

    def test_build_set_controls_locked(self):
        state = FridgeState(powered_on=True, controls_locked=True)
        frame = build_set(state)
        assert frame[4] == 1  # controls_locked at payload[0]
        assert validate_checksum(frame)

    def test_build_set_powered_off(self):
        state = FridgeState(powered_on=False)
        frame = build_set(state)
        assert frame[5] == 0  # powered_on at payload[1]
        assert validate_checksum(frame)

    def test_build_set_negative_target(self):
        state = FridgeState(powered_on=True, unit1_target_temp=-20)
        frame = build_set(state)
        assert frame[8] == 0xEC  # -20 as unsigned
        assert validate_checksum(frame)

    def test_build_set_fahrenheit(self):
        state = FridgeState(powered_on=True, temp_unit=1)
        frame = build_set(state)
        assert frame[13] == 1  # temp_unit at payload[9]
        assert validate_checksum(frame)

    def test_build_set_all_tc_values(self):
        state = FridgeState(
            powered_on=True,
            unit1_tc_hot=5,
            unit1_tc_mid=2,
            unit1_tc_cold=-3,
            unit1_tc_halt=-5,
        )
        frame = build_set(state)
        assert frame[14] == 5     # tc_hot
        assert frame[15] == 2     # tc_mid
        assert frame[16] == 0xFD  # tc_cold = -3
        assert frame[17] == 0xFB  # tc_halt = -5
        assert validate_checksum(frame)

    def test_build_set_roundtrip(self):
        """Build a Set, parse the response, verify fields match."""
        state = FridgeState(
            powered_on=True,
            run_mode=0,
            unit1_target_temp=3,
            temp_max=20,
            temp_min=-20,
            unit1_hysteresis=2,
            unit1_tc_cold=-3,
        )
        frame = build_set(state)
        # Simulate fridge echoing back with cmd=0x02 and full 18-byte payload
        # (fridge adds current_temp, battery, etc.)
        response_payload = bytes(frame[4:]) + bytes([
            4,   # unit1_current_temp
            100, # battery_percent
            13,  # battery_volt_int
            9,   # battery_volt_frac
        ])
        response = (
            b"\xFE\xFE"
            + bytes([1 + len(response_payload) + 2, CMD_SET])
            + response_payload
            + b"\x00\x00"
        )
        parsed = parse_response(response)
        assert parsed is not None
        assert parsed.powered_on is True
        assert parsed.unit1_target_temp == 3
        assert parsed.unit1_tc_cold == -3


class TestFuzz:
    """Fuzz-style tests for robustness against malformed frames."""

    def test_all_zeros(self):
        assert parse_response(bytes(50)) is None
        assert not validate_frame(bytes(50))

    def test_all_0xff(self):
        assert parse_response(bytes([0xFF] * 50)) is None
        assert not validate_frame(bytes([0xFF] * 50))

    def test_header_only(self):
        assert parse_response(b"\xFE\xFE") is None
        assert not validate_frame(b"\xFE\xFE")

    def test_header_plus_huge_length(self):
        """Length field claims 255 bytes but frame is short."""
        frame = b"\xFE\xFE\xFF\x01" + bytes(10)
        assert parse_response(frame) is None
        assert not validate_frame(frame)

    def test_header_plus_zero_length(self):
        """Length field is zero."""
        frame = b"\xFE\xFE\x00"
        assert parse_response(frame) is None
        assert not validate_frame(frame)

    def test_embedded_headers(self):
        """Data containing 0xFEFE inside payload - assembler waits for declared length."""
        asm = FrameAssembler()
        # Garbage claims length 0x50 (80), so assembler buffers until 83 bytes.
        # The valid query appended is swallowed as part of the "bad frame".
        garbage = b"\xFE\xFE\x50" + b"\xFE\xFE" * 10  # 23 bytes, claims 83
        frames = asm.feed(garbage + build_query())
        # Assembler is still waiting for the 83-byte frame to complete
        assert len(frames) == 0
        # But feeding a fresh valid frame after the buffer is flushed works
        asm2 = FrameAssembler()
        frames = asm2.feed(b"\x00\x01\x02" + build_query())
        assert len(frames) == 1
        assert frames[0] == build_query()

    def test_truncated_payload(self):
        """Valid header and length but truncated before payload ends."""
        frame = b"\xFE\xFE\x15\x01" + bytes(5)  # claims 21 bytes, only 5
        assert parse_response(frame) is None
        assert not validate_frame(frame)

    def test_single_byte_frames(self):
        """Every single byte value should be safe to parse."""
        for b in range(256):
            assert parse_response(bytes([b])) is None

    def test_assembler_garbage_flood(self):
        """Assembler stays stable after lots of garbage."""
        asm = FrameAssembler()
        import os
        garbage = os.urandom(10000)
        asm.feed(garbage)
        # Should still work after garbage
        frames = asm.feed(build_query())
        # May or may not find the query depending on garbage content,
        # but must not crash
        assert isinstance(frames, list)

    def test_assembler_repeated_headers(self):
        """Stream of just 0xFE bytes - assembler treats 0xFE as length field."""
        asm = FrameAssembler()
        frames = asm.feed(b"\xFE" * 1000)
        assert isinstance(frames, list)
        # 0xFEFE header + 0xFE length (254) = 257-byte "frames" are extracted
        # 1000 / 257 = ~3 frames consumed, which is expected behavior
        assert len(frames) >= 1

    def test_length_field_one(self):
        """Minimal length field (1) = 4 bytes total, below validate_frame min of 5."""
        frame = b"\xFE\xFE\x01\x01"
        assert parse_response(frame) is None
        assert not validate_frame(frame)  # too short (< 5 bytes)

    def test_parse_response_does_not_modify_input(self):
        """Ensure parse_response doesn't mutate the input bytes."""
        original = bytes(DOC_RESPONSE)
        copy = bytearray(original)
        parse_response(original)
        assert original == bytes(copy)
