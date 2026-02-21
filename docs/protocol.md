# Alpicool Fridge BLE Protocol Reference

Reference for building the ESPHome external component.
Sources: klightspeed/BrassMonkeyFridgeMonitor, johnelliott/alpicoold, oh2mp/esp32_ble2mqtt

## BLE Details

- Service: `0x1234`
- Write (commands): `0x1235`
- Notify (responses): `0x1236`
- No auth/pairing required
- Connecting locks out other BLE clients
- Device names: `WT-0001`, `A1-*`, `AK1-*`, `AK2-*`, `AK3-*`
- Advertisement contains "ZHJIELI" at payload offset 9 (for identification)
- Cannot read state passively - must connect and query

## Frame Format

```
[0xFE] [0xFE] [length] [command] [payload...] [checksum_hi] [checksum_lo]
```

- Length = number of bytes following (cmd + payload + 2-byte checksum)
- Checksum = big-endian 16-bit sum of ALL preceding bytes
- **BUG**: Some firmware sends checksum*2. Must accept both!

## Commands

| Code | Name | Description |
|------|------|-------------|
| 0x00 | Bind | Display "APP", wait for button press |
| 0x01 | Query | Request current state |
| 0x02 | Set | Modify settings (14 bytes single, 25 bytes dual) |
| 0x04 | Reset | Reset device |
| 0x05 | SetUnit1Target | Set Zone 1 target temp |
| 0x06 | SetUnit2Target | Set Zone 2 target temp |

## Query Command

Always: `FE FE 03 01 02 00`

## Query Response - Single Zone (payload offsets, after cmd byte)

| Offset | Field | Type | Notes |
|--------|-------|------|-------|
| 0x00 | controls_locked | bool | |
| 0x01 | powered_on | bool | |
| 0x02 | run_mode | uint8 | 0=Max, 1=Eco |
| 0x03 | battery_saver | uint8 | 0=Low, 1=Mid, 2=High cutoff |
| 0x04 | unit1_target_temp | int8 | Signed! |
| 0x05 | temp_max | int8 | Max selectable |
| 0x06 | temp_min | int8 | Min selectable |
| 0x07 | unit1_hysteresis | int8 | Return differential |
| 0x08 | start_delay | uint8 | Minutes |
| 0x09 | temp_unit | uint8 | 0=C, 1=F |
| 0x0A | unit1_tc_hot | int8 | Correction >= -6C |
| 0x0B | unit1_tc_mid | int8 | Correction -12C to -6C |
| 0x0C | unit1_tc_cold | int8 | Correction < -12C |
| 0x0D | unit1_tc_halt | int8 | Correction when halted |
| 0x0E | unit1_current_temp | int8 | **Current temperature** |
| 0x0F | battery_percent | uint8 | 0x7F = unknown/mains |
| 0x10 | battery_volt_int | uint8 | Integer part |
| 0x11 | battery_volt_frac | uint8 | Tenths (voltage = int + frac/10) |

## Query Response - Dual Zone Extension (payload >= 28 bytes)

| Offset | Field | Type |
|--------|-------|------|
| 0x12 | unit2_target_temp | int8 |
| 0x13-0x14 | reserved | - |
| 0x15 | unit2_hysteresis | int8 |
| 0x16 | unit2_tc_hot | int8 |
| 0x17 | unit2_tc_mid | int8 |
| 0x18 | unit2_tc_cold | int8 |
| 0x19 | unit2_tc_halt | int8 |
| 0x1A | unit2_current_temp | int8 |
| 0x1B | running_status | uint8 |

Detection: payload >= 28 bytes = dual-zone.

## Set Command Payload (Single-Zone, 14 bytes after cmd)

```
cmd(0x02), locked(bool), powered(bool), run_mode(u8), bat_saver(u8),
target(i8), max_temp(i8), min_temp(i8), hysteresis(i8),
start_delay(u8), temp_unit(u8),
tc_hot(i8), tc_mid(i8), tc_cold(i8), tc_halt(i8)
```

## Test Vectors

### Query command
```
FE FE 03 01 02 00
```

### Query response (single-zone, -15C target, -13C current, 12.3V, 100%)
```
FE FE 15 01 00 01 00 00 F1 14 EC 02 00 00 00 00 00 00 F3 64 0C 03 05 6C
```
Parse: locked=false, powered=true, mode=Max, saver=Low,
target=-15, max=20, min=-20, hyst=2, delay=0, unit=C,
corrections=0, current=-13, bat=100%, voltage=12.3V

### Set target to -18C
```
FE FE 04 05 EE 02 F3
```

## Key Implementation Notes

1. **Checksum variant**: Reference says accept both `sum` and `sum*2`. Our A1-4X
   fridge sends trailing bytes that match neither -- they appear to encode
   operational state (high byte correlates with compressor running). Accept any
   trailing bytes; validate only by header and length field.
2. **BLE fragmentation**: Buffer partial packets, reassemble by length field.
   Query responses (24 bytes) arrive as 20+4 fragments at default ATT MTU.
3. **Reconnect retry**: 2-3 attempts, "failed to discover services" is common
4. **Write with response**: Use ESP_GATT_WRITE_TYPE_RSP
5. **Poll interval**: 10s default, 5s query timeout
6. **Connect-query-disconnect**: Alternative pattern used by oh2mp (saves power)
7. **Battery unknown**: 0x7F (127) means no battery monitoring (mains model)
8. **Signed temps**: All temperature fields are int8_t
9. **Raw byte offsets**: raw[N] = payload[N-4] (4-byte header: FE FE len cmd)
10. **Set response**: The Set (0x02) command echoes back full state (same as
    Query) with cmd=0x02. SetUnit1Target (0x05) echoes cmd+target only.
11. **Extra characteristic**: 0xFFF1 (write, notify) exists but purpose unknown.
    Subscribing may cause BLE disconnection on some firmwares.

## Fuzzing Targets

- Empty/short packets (< 5 bytes)
- Wrong header (not FE FE)
- Length mismatch (claims more/fewer bytes than actual)
- Wrong checksum, doubled checksum, zero checksum
- Unknown command codes
- Payload too short for single-zone (< 18 bytes)
- Boundary int8 values: 0x7F (127), 0x80 (-128)
- Split packet at every byte boundary
