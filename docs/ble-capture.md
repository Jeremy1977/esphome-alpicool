# Alpicool BLE Capture Results

**Date**: 2026-02-22 01:12:55
**Device**: XX:XX:XX:XX:XX:XX (A1-4X...)
**Service**: 0x1234
**Write char**: 0x1235
**Notify char**: 0x1236
**Extra char**: 0xFFF1 (write, notify) -- not in reference docs

## Key Protocol Findings

### Trailing bytes are NOT a standard checksum

The reference implementation (BrassMonkeyFridgeMonitor) describes the last 2 bytes
of each packet as a big-endian 16-bit sum-of-bytes checksum, with a note that some
firmware sends checksum*2.

This A1-4X firmware does NOT use a standard checksum. The trailing 2 bytes do not
match the sum of preceding bytes, nor the doubled sum. They vary between packets
even when the payload is identical, and they change dramatically when the fridge
is powered off vs on:

| State | Trailing values observed |
|-------|-------------------------|
| Powered on, compressor running | `13 54`, `13 7F`, `13 B3`, `13 79`, `13 BA`, `13 E5`, `13 47`, `13 76` |
| After power off | `09 1E`, `09 26` |
| After power back on | `13 47` |
| After target temp change | `12 82`, `12 81`, `12 82` |

The high byte drops from ~0x13 to 0x09 when the fridge is powered off, suggesting
it may encode compressor duty cycle, runtime, or some other operational metric.
The low byte varies independently and may be a packet counter or timestamp.

**Implementation note**: Accept all well-framed packets (valid FE FE header and
length field) regardless of trailing bytes. The fridge accepts commands with
standard checksums on the outbound side (our sent packets use sum-of-bytes and
are accepted without issue).

### BLE MTU fragmentation

Query responses are 24 bytes but arrive in 2 fragments (20 + 4 bytes) due to
the default BLE ATT MTU of 23 bytes. Implementations must reassemble using the
length field at offset 2.

### Undocumented command 0x03

Command 0x03 is not in the BrassMonkey reference docs. This fridge responds to it:

- Sent: `FE FE 03 03 02 02`
- Response payload: `03 01 04 04 04`
- Interpretation: possibly firmware/hardware version (1.4.4.4?)

### Set (0x02) echoes full state

When a Set command is sent, the fridge responds with the full state payload
(same 18-byte format as a Query response), but with command byte 0x02 instead
of 0x01. This serves as both an acknowledgment and a state verification.

### SetUnit1Target (0x05) compact ACK

The SetUnit1Target response echoes just 2 bytes: the command (0x05) and the
accepted target temperature. Much more compact than the Set (0x02) response.

### Bind (0x00) does not respond

The Bind command timed out with no response. The fridge may require a physical
button press on the unit for the bind flow to complete, or this firmware may
not implement it.

### Extra characteristic 0xFFF1

This fridge exposes an additional characteristic `0xFFF1` with write+notify
properties, not documented in the BrassMonkey reference. Its purpose is unknown.
Subscribing to notifications on it caused a BLE disconnection during our test.

### Single-zone only

All responses had 18-byte payloads (less than the 28-byte threshold for
dual-zone), confirming this is a single-zone fridge.

## All Captures

### 1. Query #1

**Sent**: `FE FE 03 01 02 00`
**Received**: `FE FE 15 01 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 13 54`
**Payload**: `01000100000314ec0200000000fd0004640d09`
**Trailing**: `1354`

| Field | Value |
|-------|-------|
| controls_locked | False |
| powered_on | True |
| run_mode | Max |
| run_mode_raw | 0 |
| battery_saver | Low |
| battery_saver_raw | 0 |
| unit1_target_temp | 3 |
| temp_max | 20 |
| temp_min | -20 |
| unit1_hysteresis | 2 |
| start_delay | 0 |
| temp_unit | C |
| temp_unit_raw | 0 |
| unit1_tc_hot | 0 |
| unit1_tc_mid | 0 |
| unit1_tc_cold | -3 |
| unit1_tc_halt | 0 |
| unit1_current_temp | 4 |
| battery_percent | 100 |
| battery_volt_int | 13 |
| battery_volt_frac | 9 |
| battery_voltage | 13.9 |
| dual_zone | False |

---

### 2. Query #2

**Sent**: `FE FE 03 01 02 00`
**Received**: `FE FE 15 01 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 13 7F`
**Payload**: `01000100000314ec0200000000fd0004640d09`
**Trailing**: `137f`

| Field | Value |
|-------|-------|
| controls_locked | False |
| powered_on | True |
| run_mode | Max |
| run_mode_raw | 0 |
| battery_saver | Low |
| battery_saver_raw | 0 |
| unit1_target_temp | 3 |
| temp_max | 20 |
| temp_min | -20 |
| unit1_hysteresis | 2 |
| start_delay | 0 |
| temp_unit | C |
| temp_unit_raw | 0 |
| unit1_tc_hot | 0 |
| unit1_tc_mid | 0 |
| unit1_tc_cold | -3 |
| unit1_tc_halt | 0 |
| unit1_current_temp | 4 |
| battery_percent | 100 |
| battery_volt_int | 13 |
| battery_volt_frac | 9 |
| battery_voltage | 13.9 |
| dual_zone | False |

---

### 3. SetUnit1Target(4C)

**Sent**: `FE FE 04 05 04 02 09`
**Received**: `FE FE 04 05 04 13 B3`
**Payload**: `0504`
**Trailing**: `13b3`

| Field | Value |
|-------|-------|
| command_echo | 0x05 |
| data | 04 |

---

### 4. Query (verify changed)

**Sent**: `FE FE 03 01 02 00`
**Received**: `FE FE 15 01 00 01 00 00 04 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 12 82`
**Payload**: `01000100000414ec0200000000fd0004640d09`
**Trailing**: `1282`

| Field | Value |
|-------|-------|
| controls_locked | False |
| powered_on | True |
| run_mode | Max |
| run_mode_raw | 0 |
| battery_saver | Low |
| battery_saver_raw | 0 |
| unit1_target_temp | 4 |
| temp_max | 20 |
| temp_min | -20 |
| unit1_hysteresis | 2 |
| start_delay | 0 |
| temp_unit | C |
| temp_unit_raw | 0 |
| unit1_tc_hot | 0 |
| unit1_tc_mid | 0 |
| unit1_tc_cold | -3 |
| unit1_tc_halt | 0 |
| unit1_current_temp | 4 |
| battery_percent | 100 |
| battery_volt_int | 13 |
| battery_volt_frac | 9 |
| battery_voltage | 13.9 |
| dual_zone | False |

---

### 5. SetUnit1Target(3C) restore

**Sent**: `FE FE 04 05 03 02 08`
**Received**: `FE FE 04 05 03 12 81`
**Payload**: `0503`
**Trailing**: `1281`

| Field | Value |
|-------|-------|
| command_echo | 0x05 |
| data | 03 |

---

### 6. Query (verify restored)

**Sent**: `FE FE 03 01 02 00`
**Received**: `FE FE 15 01 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 12 82`
**Payload**: `01000100000314ec0200000000fd0004640d09`
**Trailing**: `1282`

| Field | Value |
|-------|-------|
| controls_locked | False |
| powered_on | True |
| run_mode | Max |
| run_mode_raw | 0 |
| battery_saver | Low |
| battery_saver_raw | 0 |
| unit1_target_temp | 3 |
| temp_max | 20 |
| temp_min | -20 |
| unit1_hysteresis | 2 |
| start_delay | 0 |
| temp_unit | C |
| temp_unit_raw | 0 |
| unit1_tc_hot | 0 |
| unit1_tc_mid | 0 |
| unit1_tc_cold | -3 |
| unit1_tc_halt | 0 |
| unit1_current_temp | 4 |
| battery_percent | 100 |
| battery_volt_int | 13 |
| battery_volt_frac | 9 |
| battery_voltage | 13.9 |
| dual_zone | False |

---

### 7. Set (mode -> Eco)

**Sent**: `FE FE 11 02 00 01 01 00 03 14 EC 02 00 00 00 00 FD 00 04 13`
**Received**: `FE FE 15 02 00 01 01 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 13 79`
**Payload**: `02000101000314ec0200000000fd0004640d09`
**Trailing**: `1379`

| Field | Value |
|-------|-------|
| command_echo | 0x02 |
| data | 000101000314ec0200000000fd0004640d09 |

---

### 8. Query (verify mode)

**Sent**: `FE FE 03 01 02 00`
**Received**: `FE FE 15 01 00 01 01 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 14 13`
**Payload**: `01000101000314ec0200000000fd0004640d09`
**Trailing**: `1413`

| Field | Value |
|-------|-------|
| controls_locked | False |
| powered_on | True |
| run_mode | Eco |
| run_mode_raw | 1 |
| battery_saver | Low |
| battery_saver_raw | 0 |
| unit1_target_temp | 3 |
| temp_max | 20 |
| temp_min | -20 |
| unit1_hysteresis | 2 |
| start_delay | 0 |
| temp_unit | C |
| temp_unit_raw | 0 |
| unit1_tc_hot | 0 |
| unit1_tc_mid | 0 |
| unit1_tc_cold | -3 |
| unit1_tc_halt | 0 |
| unit1_current_temp | 4 |
| battery_percent | 100 |
| battery_volt_int | 13 |
| battery_volt_frac | 9 |
| battery_voltage | 13.9 |
| dual_zone | False |

---

### 9. Set (mode -> Max) restore

**Sent**: `FE FE 11 02 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 12`
**Received**: `FE FE 15 02 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 13 BA`
**Payload**: `02000100000314ec0200000000fd0004640d09`
**Trailing**: `13ba`

| Field | Value |
|-------|-------|
| command_echo | 0x02 |
| data | 000100000314ec0200000000fd0004640d09 |

---

### 10. Query (verify mode restored)

**Sent**: `FE FE 03 01 02 00`
**Received**: `FE FE 15 01 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 13 E5`
**Payload**: `01000100000314ec0200000000fd0004640d09`
**Trailing**: `13e5`

| Field | Value |
|-------|-------|
| controls_locked | False |
| powered_on | True |
| run_mode | Max |
| run_mode_raw | 0 |
| battery_saver | Low |
| battery_saver_raw | 0 |
| unit1_target_temp | 3 |
| temp_max | 20 |
| temp_min | -20 |
| unit1_hysteresis | 2 |
| start_delay | 0 |
| temp_unit | C |
| temp_unit_raw | 0 |
| unit1_tc_hot | 0 |
| unit1_tc_mid | 0 |
| unit1_tc_cold | -3 |
| unit1_tc_halt | 0 |
| unit1_current_temp | 4 |
| battery_percent | 100 |
| battery_volt_int | 13 |
| battery_volt_frac | 9 |
| battery_voltage | 13.9 |
| dual_zone | False |

---

### 11. Set (power OFF)

**Sent**: `FE FE 11 02 00 00 00 00 03 14 EC 02 00 00 00 00 FD 00 04 11`
**Received**: `FE FE 15 02 00 00 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 14 1C`
**Payload**: `02000000000314ec0200000000fd0004640d09`
**Trailing**: `141c`

| Field | Value |
|-------|-------|
| command_echo | 0x02 |
| data | 000000000314ec0200000000fd0004640d09 |

---

### 12. Query (verify OFF)

**Sent**: `FE FE 03 01 02 00`
**Received**: `FE FE 15 01 00 00 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 09 1E`
**Payload**: `01000000000314ec0200000000fd0004640d09`
**Trailing**: `091e`

| Field | Value |
|-------|-------|
| controls_locked | False |
| powered_on | False |
| run_mode | Max |
| run_mode_raw | 0 |
| battery_saver | Low |
| battery_saver_raw | 0 |
| unit1_target_temp | 3 |
| temp_max | 20 |
| temp_min | -20 |
| unit1_hysteresis | 2 |
| start_delay | 0 |
| temp_unit | C |
| temp_unit_raw | 0 |
| unit1_tc_hot | 0 |
| unit1_tc_mid | 0 |
| unit1_tc_cold | -3 |
| unit1_tc_halt | 0 |
| unit1_current_temp | 4 |
| battery_percent | 100 |
| battery_volt_int | 13 |
| battery_volt_frac | 9 |
| battery_voltage | 13.9 |
| dual_zone | False |

---

### 13. Set (power ON)

**Sent**: `FE FE 11 02 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 12`
**Received**: `FE FE 15 02 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 09 26`
**Payload**: `02000100000314ec0200000000fd0004640d09`
**Trailing**: `0926`

| Field | Value |
|-------|-------|
| command_echo | 0x02 |
| data | 000100000314ec0200000000fd0004640d09 |

---

### 14. Query (verify ON)

**Sent**: `FE FE 03 01 02 00`
**Received**: `FE FE 15 01 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 13 47`
**Payload**: `01000100000314ec0200000000fd0004640d09`
**Trailing**: `1347`

| Field | Value |
|-------|-------|
| controls_locked | False |
| powered_on | True |
| run_mode | Max |
| run_mode_raw | 0 |
| battery_saver | Low |
| battery_saver_raw | 0 |
| unit1_target_temp | 3 |
| temp_max | 20 |
| temp_min | -20 |
| unit1_hysteresis | 2 |
| start_delay | 0 |
| temp_unit | C |
| temp_unit_raw | 0 |
| unit1_tc_hot | 0 |
| unit1_tc_mid | 0 |
| unit1_tc_cold | -3 |
| unit1_tc_halt | 0 |
| unit1_current_temp | 4 |
| battery_percent | 100 |
| battery_volt_int | 13 |
| battery_volt_frac | 9 |
| battery_voltage | 13.9 |
| dual_zone | False |

---

### 15. Probe 0x03

**Sent**: `FE FE 03 03 02 02`
**Received**: `FE FE 07 03 01 04 04 04 13 76`
**Payload**: `0301040404`
**Trailing**: `1376`

| Field | Value |
|-------|-------|
| command_echo | 0x03 |
| data | 01040404 |

---

### 16. Probe 0x07

**Sent**: `FE FE 03 07 02 06`
**Result**: no response within 2.0s

---

### 17. Probe 0x08

**Sent**: `FE FE 03 08 02 07`
**Result**: no response within 2.0s

---

### 18. Probe 0x09

**Sent**: `FE FE 03 09 02 08`
**Result**: no response within 2.0s

---

### 19. Probe 0x0A

**Sent**: `FE FE 03 0A 02 09`
**Result**: no response within 2.0s

---

### 20. Probe 0x0B

**Sent**: `FE FE 03 0B 02 0A`
**Result**: no response within 2.0s

---

### 21. Probe 0x0C

**Sent**: `FE FE 03 0C 02 0B`
**Result**: no response within 2.0s

---

### 22. Probe 0x0D

**Sent**: `FE FE 03 0D 02 0C`
**Result**: no response within 2.0s

---

### 23. Probe 0x0E

**Sent**: `FE FE 03 0E 02 0D`
**Result**: no response within 2.0s

---

### 24. Probe 0x0F

**Sent**: `FE FE 03 0F 02 0E`
**Result**: no response within 2.0s

---

### 25. Bind (0x00)

**Sent**: `FE FE 03 00 01 FF`
**Result**: no response within 3.0s

---

### 26. Query (final)

**Sent**: `FE FE 03 01 02 00`
**Result**: write failed: Service Discovery has not been performed yet

---

## State Readings Summary

| # | Label | Current | Target | Mode | Power | Battery V | Battery % |
|---|-------|---------|--------|------|-------|-----------|-----------|
| 1 | Query #1 | 4C | 3C | Max | ON | 13.9V | 100% |
| 2 | Query #2 | 4C | 3C | Max | ON | 13.9V | 100% |
| 3 | Query (verify changed) | 4C | 4C | Max | ON | 13.9V | 100% |
| 4 | Query (verify restored) | 4C | 3C | Max | ON | 13.9V | 100% |
| 5 | Query (verify mode) | 4C | 3C | Eco | ON | 13.9V | 100% |
| 6 | Query (verify mode restored) | 4C | 3C | Max | ON | 13.9V | 100% |
| 7 | Query (verify OFF) | 4C | 3C | Max | OFF | 13.9V | 100% |
| 8 | Query (verify ON) | 4C | 3C | Max | ON | 13.9V | 100% |

## Commands That Work

| Command | Sent | Response |
|---------|------|----------|
| Query #1 | `FE FE 03 01 02 00` | `FE FE 15 01 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 13 54` |
| Query #2 | `FE FE 03 01 02 00` | `FE FE 15 01 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 13 7F` |
| SetUnit1Target(4C) | `FE FE 04 05 04 02 09` | `FE FE 04 05 04 13 B3` |
| Query (verify changed) | `FE FE 03 01 02 00` | `FE FE 15 01 00 01 00 00 04 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 12 82` |
| SetUnit1Target(3C) restore | `FE FE 04 05 03 02 08` | `FE FE 04 05 03 12 81` |
| Query (verify restored) | `FE FE 03 01 02 00` | `FE FE 15 01 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 12 82` |
| Set (mode -> Eco) | `FE FE 11 02 00 01 01 00 03 14 EC 02 00 00 00 00 FD 00 04 13` | `FE FE 15 02 00 01 01 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 13 79` |
| Query (verify mode) | `FE FE 03 01 02 00` | `FE FE 15 01 00 01 01 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 14 13` |
| Set (mode -> Max) restore | `FE FE 11 02 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 12` | `FE FE 15 02 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 13 BA` |
| Query (verify mode restored) | `FE FE 03 01 02 00` | `FE FE 15 01 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 13 E5` |
| Set (power OFF) | `FE FE 11 02 00 00 00 00 03 14 EC 02 00 00 00 00 FD 00 04 11` | `FE FE 15 02 00 00 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 14 1C` |
| Query (verify OFF) | `FE FE 03 01 02 00` | `FE FE 15 01 00 00 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 09 1E` |
| Set (power ON) | `FE FE 11 02 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 12` | `FE FE 15 02 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 09 26` |
| Query (verify ON) | `FE FE 03 01 02 00` | `FE FE 15 01 00 01 00 00 03 14 EC 02 00 00 00 00 FD 00 04 64 0D 09 13 47` |
| Probe 0x03 | `FE FE 03 03 02 02` | `FE FE 07 03 01 04 04 04 13 76` |

## Commands That Timed Out

| Command | Sent |
|---------|------|
| Probe 0x07 | `FE FE 03 07 02 06` |
| Probe 0x08 | `FE FE 03 08 02 07` |
| Probe 0x09 | `FE FE 03 09 02 08` |
| Probe 0x0A | `FE FE 03 0A 02 09` |
| Probe 0x0B | `FE FE 03 0B 02 0A` |
| Probe 0x0C | `FE FE 03 0C 02 0B` |
| Probe 0x0D | `FE FE 03 0D 02 0C` |
| Probe 0x0E | `FE FE 03 0E 02 0D` |
| Probe 0x0F | `FE FE 03 0F 02 0E` |
| Bind (0x00) | `FE FE 03 00 01 FF` |
