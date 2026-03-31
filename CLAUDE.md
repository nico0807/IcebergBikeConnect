# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based dashboard and client for iSuper gym bikes. The project implements a custom ASCII-based protocol to connect to gym bikes via WiFi, control resistance levels, and display real-time workout data in a terminal-based UI.

**Key Components:**
- [isuper_bike.py](isuper_bike.py) - Core protocol client handling bike connection and data parsing
- [dashboard.py](dashboard.py) - Terminal-based curses UI for real-time monitoring
- [dashboard_gui.py](dashboard_gui.py) - Dear PyGui graphical UI for real-time monitoring
- [sport_program_parser.py](sport_program_parser.py) - Parser for structured workout programs
- [wake_keeper.py](wake_keeper.py) - OS-level screen wake lock shared by both dashboards (prevents display sleep during workouts)

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
- `--list-ips` - Scan local network for bikes
- `--configure-ap <SSID>` - Configure bike to connect to a WiFi network (requires password prompt)
- `--no-wake-lock` - Disable automatic screen wake prevention (enabled by default)

### Quick Connection

```bash
# Scan for bikes
python dashboard.py --list-ips

# Connect to specific IP
python dashboard.py --ip 192.168.4.1

# With debug output (automatically logged to debug_logs/ directory)
python dashboard.py --ip 192.168.4.1
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
- Start: Send `<CP_000>` - this starts the activity and bike automatically sends sport data periodically
- Data: Bike automatically sends `<W6_DATA>` responses after `CP_000`
- Stop: Send `<CP_300>` - this stops the activity and bike stops sending sport data
- Set level: Send `<CR_nn>` where nn is level 00-99 (zero-padded)

**Sport Data Format (`<W6_SYNC,DISTANCE,RPM,PULSE,LEVEL,CALORIES,POWER,UNKNOWN>`):**
- Distance requires wrap-around handling (counter resets at 1000)
- Speed is derived: `speed = rpm * 55 * 0.00478536`
- Calories: `raw_calories / 100`

### Class Structure

**`ISuperBike` class ([isuper_bike.py](isuper_bike.py)):**
- Manages TCP connection to bike
- Handles protocol initialization sequence
- Parses incoming ASCII commands via `parse_command()`
- Receives sport data automatically from bike using `receive_sport_data()` (passive mode)
- Thread-safe data access via `lock` attribute
- CSV logging to `activity_logs/` directory

**`Dashboard` class ([dashboard.py](dashboard.py)):**
- Curses-based terminal UI
- Handles keyboard input (level control, pause/resume, program selection)
- Integrates with `SportProgram` for automated workout programs
- Receives bike data automatically (bike sends data periodically after sport mode is started)
- **`ScreenWakeKeeper` class**: Automatically prevents screen from turning off during workouts
  - Windows: Uses `powercfg` to disable monitor and standby timeouts
  - macOS: Uses `caffeinate` command to prevent display and idle sleep
  - Linux: Uses `xset` or `systemd-inhibit` to prevent sleep

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

### Debug Logging

Debug information is automatically logged to timestamped files:
- Location: `debug_logs/session_YYYYMMDD_HHMMSS.log`
- Contains all protocol communication, connection details, and error messages
- Created automatically for each session
- No command-line flags needed - logging is always enabled

## Important Notes

- **Distance Wrap-Around**: The bike's distance counter resets at 1000. The client tracks this with `hi_dist_value` to calculate cumulative distance.
- **Resistance Levels**: The bike reports min/max resistance range during init. Use `set_level()` which automatically constrains to valid range.
- **Protocol Timeout**: The bike expects responses within 200ms. No response after 30 messages = connection lost.
- **Authentication**: Password is hardcoded as `"SUPERWIGH"`.
- **Level Zero-Indexing**: `CR_00` corresponds to Level 1, so the code subtracts 1 when setting levels.
- **CR_00 Firmware Bug**: `CR_00` (Level 1) is broken on the bike — the bike ignores the command (no ACK) and reports ~10x the correct power when at level 1, corrupting calories too. `set_level()` skips `CR_00` entirely and uses `CR_01` as the minimum, so UI levels 1 and 2 both map to `CR_01` on the wire.
- **Screen Wake Lock**: The dashboard automatically prevents your screen from turning off during workouts. This is enabled by default but can be disabled with `--no-wake-lock`. Original system sleep settings are automatically restored when the dashboard exits.
