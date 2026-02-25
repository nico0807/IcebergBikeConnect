# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based dashboard and client for iSuper gym bikes. The project implements a custom ASCII-based protocol to connect to gym bikes via WiFi, control resistance levels, and display real-time workout data in a terminal-based UI.

**Key Components:**
- [isuper_bike.py](isuper_bike.py) - Core protocol client handling bike connection and data parsing
- [dashboard.py](dashboard.py) - Terminal-based curses UI for real-time monitoring
- [sport_program_parser.py](sport_program_parser.py) - Parser for structured workout programs

## Running the Project

### Prerequisites

```bash
# Install curses (required for dashboard)
pip install windows-curses  # Windows
# On Linux/macOS, curses is usually pre-installed
```

### Start the Dashboard

```bash
python dashboard.py [options]
```

**Options:**
- `--ip <IP>` - Bike IP address (default: `169.254.1.1` : The P2P mode default)
- `--debug` - Enable debug logging to console
- `--list-ips` - Scan local network for bikes
- `--configure-ap <SSID>` - Configure bike to connect to a WiFi network (requires password prompt)

### Quick Connection

```bash
# Scan for bikes
python dashboard.py --list-ips

# Connect to specific IP
python dashboard.py --ip 192.168.4.1

# With debug output
python dashboard.py --ip 192.168.4.1 --debug
```

## Architecture

### Protocol Communication ([ISUPER_BIKE_PROTOCOL.md](ISUPER_BIKE_PROTOCOL.md))

The bike uses a custom ASCII-based protocol over TCP port 1971:

**Connection Sequence:**
1. Connect to bike via TCP on port 1971
2. Send `<EQ_>` to start initialization
3. Receive password `<EP_SUPERWIGH>` and acknowledge
4. Receive device info: resistance range (`<ER_MIN-MAX>`), wheel diameter (`<ED_DIA>`), MAC (`<EA_HEX>`)
5. End init with `<Ez_OK>` and pause sport with `<CP_300>`

**Sport Mode:**
- Start: Send `<WB_6>` followed by `<CP_000>`
- Poll data: Send `<WB_6>` every 200ms, receive `<W6_DATA>` response
- Set level: Send `<CR_nn>` where nn is level 00-99 (zero-padded)
- Pause: Send `<CP_300>`

**Sport Data Format (`<W6_SYNC,DISTANCE,RPM,PULSE,LEVEL,CALORIES,POWER,UNKNOWN>`):**
- Distance requires wrap-around handling (counter resets at 1000)
- Speed is derived: `speed = rpm * 55 * 0.00478536`
- Calories: `raw_calories / 100`

### Class Structure

**`ISuperBike` class ([isuper_bike.py](isuper_bike.py)):**
- Manages TCP connection to bike
- Handles protocol initialization sequence
- Parses incoming ASCII commands via `parse_command()`
- Manages sport data updates with `update_data()`
- Thread-safe data access via `lock` attribute
- CSV logging to `activity_logs/` directory

**`Dashboard` class ([dashboard.py](dashboard.py)):**
- Curses-based terminal UI
- Handles keyboard input (level control, pause/resume, program selection)
- Integrates with `SportProgram` for automated workout programs
- Auto-updates bike data at 200ms intervals

**`SportProgram` class ([sport_program_parser.py](sport_program_parser.py)):**
- Loads workout programs from `sport_programs/` directory
- Programs define segment-based resistance changes
- Tracks program progress and automatically updates bike level

### Connection Modes

The bike supports two WiFi modes:

**P2P Mode (Peer-to-Peer):**
- Bike creates its own WiFi network (e.g., "iSuper Bike", "Bike_XXXXXX")
- Your device connects directly to bike
- Fixed IP: `169.254.1.1` (or `192.168.4.1`)
- Use for quick direct connections

**AP Mode (Access point):**
- Bike connects to your existing WiFi router
- Both devices on same network
- Bike IP varies (DHCP assigned)
- Use `--ip` with the IP shown on the bike

### Sport Programs

Program files in [sport_programs/](sport_programs/) define structured workouts:

```
SEGMENTS:3
SEG:1:1
SEG:2:2
SEG:3:3
END
```

- `SEGMENTS:N` - Total number of segments
- `SEG:X:Y` - At segment X, change resistance to level Y
- Duration is user-specified when starting program (default 30 min)
- Parser automatically calculates segment duration and applies level changes

### Data Logging

Workouts are automatically logged to CSV files:
- Location: `activity_logs/workout_YYYYMMDD_HHMMSS_[program_name].csv`
- Columns: timestamp, elapsed_seconds, distance_km, speed_kmh, rpm, heart_rate_bpm, level, calories_kcal, watts
- Data logged at 1-second intervals during active sessions

## Important Notes

- **Distance Wrap-Around**: The bike's distance counter resets at 1000. The client tracks this with `hi_dist_value` to calculate cumulative distance.
- **Resistance Levels**: The bike reports min/max resistance range during init. Use `set_level()` which automatically constrains to valid range.
- **Protocol Timeout**: The bike expects responses within 200ms. No response after 30 messages = connection lost.
- **Authentication**: Password is hardcoded as `"SUPERWIGH"`.
- **Level Zero-Indexing**: `CR_00` corresponds to Level 1, so the code subtracts 1 when setting levels.
