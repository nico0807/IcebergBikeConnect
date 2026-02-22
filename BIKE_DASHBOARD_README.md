# iSuper Bike Dashboard

Python scripts to connect to and monitor iSuper gym bikes via WiFi.

## Prerequisites

```bash
pip install curses
```

## Connection Modes

The bike supports two WiFi connection modes:

### AP Mode (Access Point)
- Bike creates its own WiFi network
- Your device connects to bike's WiFi
- Default IP: `192.168.4.1` or `169.254.1.1`
- Use: `isuper_bike_simple.py` or `isuper_bike_dashboard.py`

### P2P Mode (Peer-to-Peer)
- Bike connects to your existing WiFi router
- Both devices on same network
- Bike IP varies (uses your network's DHCP)
- Use: `isuper_bike_p2p.py`

## Quick Start

### Step 1: Choose Connection Mode

**For AP Mode (default):**
1. Find bike's WiFi network (e.g., "iSuper Bike", "Bike_XXXXXX")
2. Connect your computer/phone to bike's WiFi
3. Run AP mode script

**For P2P Mode:**
1. Connect bike to your home WiFi router (via bike's settings)
2. Both your computer and bike on same network
3. Run P2P script with scan

### Step 2: Find the Bike's IP

**AP Mode:**
```bash
python isuper_bike_simple.py --scan
```

**P2P Mode:**
```bash
python isuper_bike_p2p.py --scan
```

### Step 3: Connect and Monitor

**AP Mode - Simple:**
```bash
python isuper_bike_simple.py --ip 192.168.4.1
```

**P2P Mode:**
```bash
python isuper_bike_p2p.py --scan
# or with specific IP
python isuper_bike_p2p.py --ip 192.168.1.100
```

## Scripts Reference

### `isuper_bike_simple.py` - AP Mode Console Client

Simple console client for AP mode (cross-platform).

**Commands:**
- `--ip <IP>` - Specify bike IP (default: 192.168.1.54)
- `--scan` - Scan for bikes on common AP IPs

**Interactive Controls:**
- Press `Ctrl+C` to stop
- Updates automatically every ~200ms

### `isuper_bike_p2p.py` - P2P Mode Client

Client for P2P mode where bike is on same WiFi network.

**Commands:**
- `--ip <IP>` - Specify bike IP
- `--scan` - Scan for bikes on local network
- `--timeout <N>` - Scan timeout in seconds (default: 1.0)

**How P2P Mode Works:**

In P2P mode:
1. Bike connects to your WiFi router (check bike's display for WiFi setup)
2. Bike gets an IP from your router's DHCP
3. Your computer is also on the same network
4. Script scans common IPs to find the bike

**Common P2P IPs scanned:**
- `192.168.1.1` - Router
- `192.168.0.1` - Alternative router
- `192.168.43.1` - Android hotspot
- `192.168.137.1` - Windows hotspot
- `196.254.1.1` - Link-local (sometimes)
- `169.254.1.1` - Link-local (sometimes)

### `isuper_bike_dashboard.py` - Full Dashboard

Terminal-based dashboard with real-time gauges (Linux/macOS).

**Commands:**
- `--ip <IP>` - Specify bike IP address
- `--debug` - Enable debug logging
- `--list-ips` - Scan for bikes

**Dashboard Controls:**
| Key | Action |
|-----|--------|
| `↑` / `↓` | Increase/Decrease resistance level |
| `Space` | Pause/Resume sport mode |
| `C` | Clear data (reset distance) |
| `A` | Toggle auto-update |
| `R` | Reconnect to bike |
| `Q` | Quit dashboard |

## Connection Flow

When you run any client, it:

1. **Connects** to bike on port 1971
2. **Initializes** protocol:
   - Sends `<EQ_>` to start init
   - Receives password (`SUPERWIGH`)
   - Gets resistance range (e.g., `1-20`)
   - Gets wheel diameter (e.g., `21.00"`)
   - Gets MAC/IP address
3. **Starts sport mode** with `<CP_000>`
4. **Polls data** every 200ms with `<WB_6>`
5. **Displays** real-time metrics

## Data Displayed

| Metric | Unit | Source |
|---------|-------|--------|
| Speed | km/h | RPM × 55 × 0.009 |
| RPM | rev/min | From bike |
| Heart Rate | bpm | From bike |
| Level | 1-99 | Resistance level |
| Distance | km | Calculated from wheel rotations |
| Calories | kcal | From bike |
| Power | Watts | From bike |

## Troubleshooting

### "Connection timeout"
- **AP Mode:** Make sure you're connected to bike's WiFi
- **P2P Mode:** Ensure bike is on same WiFi network
- Try scanning to find correct IP
- Check if bike is powered on

### "Connection refused"
- Bike may not be listening (check bike display)
- Wrong IP address (scan to find)
- Bike in wrong mode (AP vs P2P)

### "No bikes found" (scan mode)
- **AP Mode:** Verify WiFi connection to bike's network
- **P2P Mode:** Verify bike connected to your router
- Bike may need to be restarted
- Check bike's manual for WiFi setup
- Try longer timeout: `--timeout 2.0`

### Bike won't connect to WiFi (P2P setup)
1. Check bike's display for WiFi settings
2. Look for network setup menu
3. Enter your WiFi SSID and password
4. Wait for bike to connect
5. Scan with: `python isuper_bike_p2p.py --scan`

### Data not updating
- Bike may be in pause mode (resume with Space)
- Connection may have dropped (press R to reconnect)
- Check if bike is in standby mode

### Distance shows wrong value
- Distance resets when bike restarts
- The client handles wrap-around automatically

## AP Mode vs P2P Mode

| Feature | AP Mode | P2P Mode |
|---------|----------|-----------|
| **Setup** | Connect to bike's WiFi | Bike connects to your WiFi |
| **IP** | Fixed (`192.168.4.1`) | DHCP assigned |
| **Finding IP** | Easy (known) | Scan network |
| **Network Access** | Only bike | Full internet access |
| **Multi-device** | Limited (bike AP) | Unlimited (router) |
| **Use case** | Quick direct connection | Permanent setup |

## Protocol Reference

See [ISUPER_BIKE_PROTOCOL.md](ISUPER_BIKE_PROTOCOL.md) for full protocol documentation.

## Example Output

```
============================================================================
 iSuper Bike - P2P Mode - Real-time Data
============================================================================
  Speed:           25.5 km/h
  RPM:              85
  Heart Rate:      120 bpm
  Level:             10
  Distance:      2.456 km
  Calories:      156.3 kcal
  Power:           145 Watts
------------------------------------------------------------
  IP: 192.168.1.100 | Range: 1-20
  Wheel: 21.00" | MAC: 00:11:22:33:44:55
============================================================================
```

## Notes

- The bike uses a custom ASCII-based protocol over TCP port 1971
- Authentication password is hardcoded as `SUPERWIGH`
- The protocol expects responses within 200ms (30-message timeout)
- Sport data updates at approximately 5 Hz (every 200ms)

## Files

| File | Description | Mode |
|------|-------------|-------|
| `isuper_bike_simple.py` | Simple console client | AP |
| `isuper_bike_p2p.py` | P2P network client | P2P |
| `isuper_bike_dashboard.py` | Full dashboard with curses | Both |
| `ISUPER_BIKE_PROTOCOL.md` | Full protocol documentation | - |
| `BIKE_DASHBOARD_README.md` | This file | - |
