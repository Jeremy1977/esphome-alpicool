"""
Alpicool fridge BLE capture script.

Connects, queries status, tests set commands, probes unknown commands,
and writes all findings to a markdown document.

Discovery from first run: the A1-4X firmware uses a 2-byte trailing counter
(not a standard checksum) that increments per packet.
"""

import asyncio
import struct
import sys
import time
from enum import IntEnum
from typing import Optional

from bleak import BleakClient, BleakScanner

FRIDGE_MAC = "XX:XX:XX:XX:XX:XX"
SERVICE_UUID = "00001234-0000-1000-8000-00805f9b34fb"
WRITE_CHAR = "00001235-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR = "00001236-0000-1000-8000-00805f9b34fb"
FFF1_CHAR = "0000fff1-0000-1000-8000-00805f9b34fb"

CONNECT_TIMEOUT = 20.0
RESPONSE_TIMEOUT = 5.0


class Command(IntEnum):
    BIND = 0
    QUERY = 1
    SET = 2
    RESET = 4
    SET_UNIT1_TARGET = 5
    SET_UNIT2_TARGET = 6


def create_packet(data: bytes) -> bytes:
    """Build FE FE <len> <data...> <checksum_hi> <checksum_lo>"""
    packet = b"\xFE\xFE" + struct.pack("B", len(data) + 2) + data
    checksum = sum(packet) & 0xFFFF
    packet += struct.pack(">H", checksum)
    return packet


def hex_display(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


# Force unbuffered prints globally
_original_print = print
def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    _original_print(*args, **kwargs)


def parse_query_data(data: bytes) -> dict:
    """Parse the 18-byte data portion of a query response."""
    if len(data) < 18:
        return {"error": f"too short ({len(data)} bytes)", "raw": data.hex()}

    result = {}
    result["controls_locked"] = bool(data[0x00])
    result["powered_on"] = bool(data[0x01])
    result["run_mode"] = "Eco" if data[0x02] == 1 else "Max"
    result["run_mode_raw"] = data[0x02]
    saver_names = {0: "Low", 1: "Mid", 2: "High"}
    result["battery_saver"] = saver_names.get(data[0x03], f"Unknown({data[0x03]})")
    result["battery_saver_raw"] = data[0x03]
    result["unit1_target_temp"] = struct.unpack_from("b", data, 0x04)[0]
    result["temp_max"] = struct.unpack_from("b", data, 0x05)[0]
    result["temp_min"] = struct.unpack_from("b", data, 0x06)[0]
    result["unit1_hysteresis"] = struct.unpack_from("b", data, 0x07)[0]
    result["start_delay"] = data[0x08]
    result["temp_unit"] = "F" if data[0x09] == 1 else "C"
    result["temp_unit_raw"] = data[0x09]
    result["unit1_tc_hot"] = struct.unpack_from("b", data, 0x0A)[0]
    result["unit1_tc_mid"] = struct.unpack_from("b", data, 0x0B)[0]
    result["unit1_tc_cold"] = struct.unpack_from("b", data, 0x0C)[0]
    result["unit1_tc_halt"] = struct.unpack_from("b", data, 0x0D)[0]
    result["unit1_current_temp"] = struct.unpack_from("b", data, 0x0E)[0]
    result["battery_percent"] = data[0x0F]
    if data[0x0F] == 0x7F:
        result["battery_percent_note"] = "0x7F = unknown/mains"
    result["battery_volt_int"] = data[0x10]
    result["battery_volt_frac"] = data[0x11]
    result["battery_voltage"] = data[0x10] + data[0x11] / 10.0
    result["dual_zone"] = len(data) >= 28
    return result


def build_set_payload(state: dict, **overrides) -> bytes:
    """Build Set (0x02) command payload from a parsed state, with overrides."""
    fields = {
        "controls_locked": state.get("controls_locked", False),
        "powered_on": state.get("powered_on", True),
        "run_mode_raw": state.get("run_mode_raw", 0),
        "battery_saver_raw": state.get("battery_saver_raw", 0),
        "unit1_target_temp": state.get("unit1_target_temp", 0),
        "temp_max": state.get("temp_max", 20),
        "temp_min": state.get("temp_min", -20),
        "unit1_hysteresis": state.get("unit1_hysteresis", 2),
        "start_delay": state.get("start_delay", 0),
        "temp_unit_raw": state.get("temp_unit_raw", 0),
        "unit1_tc_hot": state.get("unit1_tc_hot", 0),
        "unit1_tc_mid": state.get("unit1_tc_mid", 0),
        "unit1_tc_cold": state.get("unit1_tc_cold", 0),
        "unit1_tc_halt": state.get("unit1_tc_halt", 0),
    }
    fields.update(overrides)
    return struct.pack(
        ">B??BBbbbbBBbbbb",
        Command.SET,
        fields["controls_locked"],
        fields["powered_on"],
        fields["run_mode_raw"],
        fields["battery_saver_raw"],
        fields["unit1_target_temp"],
        fields["temp_max"],
        fields["temp_min"],
        fields["unit1_hysteresis"],
        fields["start_delay"],
        fields["temp_unit_raw"],
        fields["unit1_tc_hot"],
        fields["unit1_tc_mid"],
        fields["unit1_tc_cold"],
        fields["unit1_tc_halt"],
    )


class Capture:
    """BLE command/response capture session."""

    def __init__(self):
        self.buffer = bytearray()
        self.event = asyncio.Event()
        self.last_packet: Optional[bytes] = None
        self.records: list[dict] = []

    def on_notify(self, sender, data: bytearray):
        print(f"  << notify ({len(data)}B): {data.hex()}")
        self.buffer.extend(data)
        # Reassemble based on length field
        if len(self.buffer) >= 3:
            expected = 3 + self.buffer[2]
            if len(self.buffer) >= expected:
                self.last_packet = bytes(self.buffer[:expected])
                self.buffer = self.buffer[expected:]
                self.event.set()

    async def send(self, client: BleakClient, name: str, data: bytes,
                   timeout: float = RESPONSE_TIMEOUT) -> dict:
        """Send a command, wait for response, return a record."""
        packet = create_packet(data)
        record = {
            "name": name,
            "sent": hex_display(packet),
            "sent_hex": packet.hex(),
            "received": None,
            "received_hex": None,
            "payload_hex": None,
            "trailing": None,
            "parsed": None,
            "error": None,
        }

        print(f"\n--- {name} ---")
        print(f"  >> send: {hex_display(packet)}")

        self.event.clear()
        self.last_packet = None

        try:
            await client.write_gatt_char(WRITE_CHAR, packet, response=True)
        except Exception as exc:
            record["error"] = f"write failed: {exc}"
            print(f"  ERROR: {record['error']}")
            self.records.append(record)
            return record

        try:
            await asyncio.wait_for(self.event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            record["error"] = f"no response within {timeout}s"
            print(f"  TIMEOUT")
            self.records.append(record)
            return record

        if self.last_packet:
            resp = self.last_packet
            record["received"] = hex_display(resp)
            record["received_hex"] = resp.hex()

            # Extract payload (skip header, length; strip trailing 2 bytes)
            length = resp[2]
            total = 3 + length
            if len(resp) >= total and total >= 5:
                payload = resp[3 : total - 2]
                trailing = resp[total - 2 : total]
                record["payload_hex"] = payload.hex()
                record["trailing"] = trailing.hex()
                print(f"  << response: {hex_display(resp)}")
                print(f"     payload: {payload.hex()}, trailing: {trailing.hex()}")

                # Parse based on command echo
                if payload and payload[0] == Command.QUERY:
                    parsed = parse_query_data(payload[1:])
                    record["parsed"] = parsed
                    for key, value in parsed.items():
                        print(f"     {key}: {value}")
                elif payload:
                    record["parsed"] = {
                        "command_echo": f"0x{payload[0]:02X}",
                        "data": payload[1:].hex() if len(payload) > 1 else "(none)",
                    }
                    print(f"     cmd=0x{payload[0]:02X} data={payload[1:].hex()}")

        self.records.append(record)
        return record


async def main():
    print("=" * 60)
    print("ALPICOOL BLE CAPTURE")
    print(f"Target: {FRIDGE_MAC}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    cap = Capture()

    # Connect directly (skipping scan -- device has weak RSSI and
    # scanning takes 10+ seconds, but direct connect works reliably)
    print("\nConnecting directly...", flush=True)
    client = BleakClient(FRIDGE_MAC, timeout=CONNECT_TIMEOUT)
    connected = False
    try:
        await client.connect()
        connected = True
        print(f"Connected: {client.is_connected}")

        # Services
        print("\nServices:")
        for svc in client.services:
            print(f"  {svc.uuid}")
            for ch in svc.characteristics:
                print(f"    {ch.uuid} [{', '.join(ch.properties)}]")

        # Subscribe
        await client.start_notify(NOTIFY_CHAR, cap.on_notify)
        await asyncio.sleep(0.5)

        # ---- QUERIES ----
        print("\n=== PHASE 1: QUERY ===")
        q1 = await cap.send(client, "Query #1", struct.pack("B", Command.QUERY))
        await asyncio.sleep(1.0)
        q2 = await cap.send(client, "Query #2", struct.pack("B", Command.QUERY))
        await asyncio.sleep(1.0)

        baseline = q1.get("parsed", {})
        if "error" in baseline:
            print(f"Query parse error: {baseline['error']}")
            print("Continuing with available data...")

        # ---- SET TARGET TEMP ----
        if "unit1_target_temp" in baseline:
            print("\n=== PHASE 2: SET TARGET TEMP ===")
            orig_target = baseline["unit1_target_temp"]
            test_target = orig_target + 1

            await cap.send(client, f"SetUnit1Target({test_target}C)",
                           struct.pack("Bb", Command.SET_UNIT1_TARGET, test_target))
            await asyncio.sleep(1.5)

            await cap.send(client, "Query (verify changed)",
                           struct.pack("B", Command.QUERY))
            await asyncio.sleep(1.0)

            await cap.send(client, f"SetUnit1Target({orig_target}C) restore",
                           struct.pack("Bb", Command.SET_UNIT1_TARGET, orig_target))
            await asyncio.sleep(1.5)

            await cap.send(client, "Query (verify restored)",
                           struct.pack("B", Command.QUERY))
            await asyncio.sleep(1.0)

        # ---- TOGGLE MODE ----
        if "run_mode_raw" in baseline:
            print("\n=== PHASE 3: TOGGLE ECO/MAX ===")
            cur_mode = baseline["run_mode_raw"]
            new_mode = 1 if cur_mode == 0 else 0
            label = "Eco" if new_mode == 1 else "Max"

            payload = build_set_payload(baseline, run_mode_raw=new_mode)
            await cap.send(client, f"Set (mode -> {label})", payload)
            await asyncio.sleep(1.5)

            await cap.send(client, "Query (verify mode)",
                           struct.pack("B", Command.QUERY))
            await asyncio.sleep(1.0)

            # Restore
            payload = build_set_payload(baseline, run_mode_raw=cur_mode)
            orig_label = "Eco" if cur_mode == 1 else "Max"
            await cap.send(client, f"Set (mode -> {orig_label}) restore", payload)
            await asyncio.sleep(1.5)

            await cap.send(client, "Query (verify mode restored)",
                           struct.pack("B", Command.QUERY))
            await asyncio.sleep(1.0)

        # ---- POWER OFF/ON ----
        if baseline.get("powered_on"):
            print("\n=== PHASE 4: POWER OFF/ON ===")

            payload = build_set_payload(baseline, powered_on=False)
            await cap.send(client, "Set (power OFF)", payload)
            await asyncio.sleep(2.0)

            await cap.send(client, "Query (verify OFF)",
                           struct.pack("B", Command.QUERY))
            await asyncio.sleep(1.0)

            payload = build_set_payload(baseline, powered_on=True)
            await cap.send(client, "Set (power ON)", payload)
            await asyncio.sleep(2.0)

            await cap.send(client, "Query (verify ON)",
                           struct.pack("B", Command.QUERY))
            await asyncio.sleep(1.0)

        # ---- PROBE UNKNOWN COMMANDS ----
        print("\n=== PHASE 5: PROBE COMMANDS ===")
        for cmd in [0x03, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F]:
            await cap.send(client, f"Probe 0x{cmd:02X}",
                           struct.pack("B", cmd), timeout=2.0)
            await asyncio.sleep(0.5)

        # ---- BIND ----
        print("\n=== PHASE 6: BIND ===")
        await cap.send(client, "Bind (0x00)",
                       struct.pack("B", Command.BIND), timeout=3.0)
        await asyncio.sleep(1.0)

        # ---- FFF1 CHARACTERISTIC ----
        print("\n=== PHASE 7: FFF1 PROBE ===")
        fff1_responses = []

        def fff1_handler(sender, data):
            print(f"  << FFF1 ({len(data)}B): {data.hex()}")
            fff1_responses.append(data.hex())

        try:
            await client.start_notify(FFF1_CHAR, fff1_handler)
            await asyncio.sleep(0.5)

            query_pkt = create_packet(struct.pack("B", Command.QUERY))
            try:
                await client.write_gatt_char(FFF1_CHAR, query_pkt, response=False)
                print(f"  >> wrote query to FFF1: {hex_display(query_pkt)}")
            except Exception as exc:
                print(f"  FFF1 write error: {exc}")
            await asyncio.sleep(2.0)

            if fff1_responses:
                cap.records.append({
                    "name": "FFF1 query probe",
                    "sent": hex_display(query_pkt),
                    "received": "; ".join(fff1_responses),
                    "parsed": {"note": "Response on 0xFFF1"},
                    "error": None,
                })

            await client.stop_notify(FFF1_CHAR)
        except Exception as exc:
            print(f"  FFF1 probe error: {exc}")

        # ---- FINAL STATE ----
        print("\n=== FINAL STATE ===")
        await cap.send(client, "Query (final)",
                       struct.pack("B", Command.QUERY))

        # Cleanup
        await client.stop_notify(NOTIFY_CHAR)

    except Exception as exc:
        print(f"\nERROR: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        if connected and client.is_connected:
            try:
                await client.disconnect()
            except Exception:
                pass  # BlueZ disconnect often throws EOFError

    # Write report
    records = cap.records
    if not records:
        print("\nNo captures to report.")
        sys.exit(1)

    report = generate_report(records)
    output = "ble-capture.md"
    with open(output, "w") as f:
        f.write(report)
    print(f"\nReport saved to {output}")
    print(f"Total captures: {len(records)}")


def generate_report(records: list[dict]) -> str:
    """Build the markdown report."""
    lines = [
        "# Alpicool BLE Capture Results",
        "",
        f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Device**: XX:XX:XX:XX:XX:XX (A1-4X...)",
        f"**Service**: 0x1234",
        f"**Write char**: 0x1235",
        f"**Notify char**: 0x1236",
        f"**Extra char**: 0xFFF1 (write, notify) -- not in reference docs",
        "",
        "## Key Protocol Findings",
        "",
        "### Trailing bytes are a counter, not a checksum",
        "",
        "The reference implementation (BrassMonkeyFridgeMonitor) describes the last 2 bytes",
        "of each packet as a big-endian 16-bit sum-of-bytes checksum, with a note that some",
        "firmware sends checksum*2.",
        "",
        "This A1-4X fridge variant does NOT use a standard checksum. The trailing 2 bytes",
        "increment per packet (observed values: `11 00`, `11 11`, `11 22`, `11 33`, ...).",
        "They do not match the sum of preceding bytes, nor the doubled sum.",
        "",
        "**Implementation note**: Accept all well-framed packets (valid FE FE header and",
        "length field) regardless of trailing bytes. The fridge still accepts commands with",
        "standard checksums on the outbound side.",
        "",
        "### BLE MTU fragmentation",
        "",
        "Query responses are 24 bytes but arrive in 2 fragments (20 + 4 bytes) due to",
        "the default BLE ATT MTU of 23 bytes. Implementations must reassemble using the",
        "length field at offset 2.",
        "",
    ]

    # Detailed captures
    lines.append("## All Captures")
    lines.append("")

    for i, rec in enumerate(records, 1):
        lines.append(f"### {i}. {rec['name']}")
        lines.append("")
        if rec.get("sent"):
            lines.append(f"**Sent**: `{rec['sent']}`")
        if rec.get("error"):
            lines.append(f"**Result**: {rec['error']}")
        if rec.get("received"):
            lines.append(f"**Received**: `{rec['received']}`")
        if rec.get("payload_hex"):
            lines.append(f"**Payload**: `{rec['payload_hex']}`")
        if rec.get("trailing"):
            lines.append(f"**Trailing**: `{rec['trailing']}`")

        if rec.get("parsed"):
            lines.append("")
            lines.append("| Field | Value |")
            lines.append("|-------|-------|")
            for key, val in rec["parsed"].items():
                lines.append(f"| {key} | {val} |")

        lines.append("")
        lines.append("---")
        lines.append("")

    # State readings summary
    queries = [r for r in records if r.get("parsed") and "unit1_current_temp" in r.get("parsed", {})]
    if queries:
        lines.append("## State Readings Summary")
        lines.append("")
        lines.append("| # | Label | Current | Target | Mode | Power | Battery V | Battery % |")
        lines.append("|---|-------|---------|--------|------|-------|-----------|-----------|")
        for i, rec in enumerate(queries, 1):
            p = rec["parsed"]
            lines.append(
                f"| {i} | {rec['name']} "
                f"| {p['unit1_current_temp']}C "
                f"| {p['unit1_target_temp']}C "
                f"| {p['run_mode']} "
                f"| {'ON' if p['powered_on'] else 'OFF'} "
                f"| {p['battery_voltage']}V "
                f"| {p['battery_percent']}% |"
            )
        lines.append("")

    # Command reference
    ok = [r for r in records if r.get("received") and not r.get("error")]
    timeout = [r for r in records if r.get("error") and "no response" in str(r.get("error", ""))]

    if ok:
        lines.append("## Commands That Work")
        lines.append("")
        lines.append("| Command | Sent | Response |")
        lines.append("|---------|------|----------|")
        for rec in ok:
            lines.append(f"| {rec['name']} | `{rec['sent']}` | `{rec['received']}` |")
        lines.append("")

    if timeout:
        lines.append("## Commands That Timed Out")
        lines.append("")
        lines.append("| Command | Sent |")
        lines.append("|---------|------|")
        for rec in timeout:
            lines.append(f"| {rec['name']} | `{rec['sent']}` |")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(main())
