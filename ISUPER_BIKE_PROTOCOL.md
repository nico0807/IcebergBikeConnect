# iSuper Gym Bike Protocol Documentation

## Overview

This document describes the communication protocol used by the iSuper Fitness app to connect to gym bikes over WiFi. The app uses a custom ASCII-based protocol over TCP sockets to control and receive data from the bike.

## Connection Details

### Network Configuration

| Parameter | Value |
|-----------|-------|
| **Default IP (Primary)** | `169.254.1.1` |
| **Default IP (Secondary)** | `196.254.1.1` |
| **Port** | `1971` (0x7B3) |
| **Protocol** | TCP |
| **Connection Timeout** | 2000ms (0x7D0) |
| **Polling Interval** | 200ms (0xC8) |

### Connection Modes

| Mode | Description |
|------|-------------|
| `P2P`  | The device is it's own access point, it will show up as a 2.4GHz Wifi AP named "iSuper-[numbershownonbike]" |
| `AP`  | Connects to a saved network (2.4GHz only) |

### Connection Timeout

- **Max Communication Counter**: 30 messages
- If device doesn't respond after 30 sent messages, connection is considered lost

## Protocol Format

All messages are ASCII strings enclosed in angle brackets `< >`:

```
<COMMAND> or <COMMAND_PARAMETER> or <COMMAND_DATA1,DATA2,...>
```

The app splits incoming data by `,` delimiter.
CRLF characters may appear in the message and must be ignored. 

## Protocol States

The original App operates in four main states which won't be used by this implemenation:

| State | Value | Description |
|-------|-------|-------------|
| `PROTOCOL_INIT` | 0 | Initialization phase |
| `PROTOCOL_IDLE` | 1 | Idle state (pause) |
| `PROTOCOL_SPORT` | 2 | Active sport mode |
| `PROTOCOL_TOAP` | 3 | Switching to Access Point mode |

## Command Reference

### Initialization Commands

| Command | Direction | Description | Response |
|---------|-----------|-------------|----------|
| `<EQ_>` | App → Bike | Start initialization | `<EQ_OK>` |
| `<EP_[PASSWORD]>` | Bike → App | Send password for auth (0)  | `<EP_OK>` |
| `<ET_[Type]>` | Bike → App | Type of equipment (ET_Upright for my bike) () | `<ET_OK>` |
| `<EM_>` | Bike → App | Memory data (2)| `<EM_OK>` |
| `<ER_[MIN-MAX]>` | Bike → App | Resistance level range (min-max)(1) | `<ER_OK>` |
| `<EA_[HEX]>` | Bike → App | MAC address | `<EA_OK>` |
| `<ED_[Diameter]>` | Bike → App | Wheel diameter * 100 | `<ED_OK>` |
| `<EU_[UNIT]>` | Bike → App | Unit type | `<EU_OK>` |
| `<Ez>` | Bike → App | End of init phase | `<Ez_OK>` |

**Authentication**: The app expects password `"SUPERWIGH"` in `<EP_>` message. If wrong, `IMClass.errorType` is set to 1.

### Control Commands

| Command | Direction | Description |
|---------|-----------|-------------|
| `<CR_nn>` | App → Bike | Set resistance level (nn = 00-99, 2 digits) |
| `<CP_000>` | App → Bike | Start / Resume sport |
| `<CP_300>` | App → Bike | Pause sport |
| `<CC_>` | App → Bike | Clear all data (resets distance) |
| `<AT_>` | App → Bike | Stop app/terminate |
| `<WB_6>` | App → Bike | Request sport data (6 bytes interval) |

### Data Request Commands

| Command | Direction | Description |
|---------|-----------|-------------|
| `<W6_OK>` | App → Bike | Acknowledge sport data |
| `<W6_[DATA]>` | Bike → App | Sport data packet |

### Access Point Mode Commands

| Command | Direction | Description |
|---------|-----------|-------------|
| `<AS_[SSID]>` | App → Bike | Send SSID for AP mode |
| `<AK_[PASSWORD]>` | App → Bike | Send AP password |
| `<AP_>` | App → Bike | Switch to AP mode |
| `<AP>` | Bike → App | AP mode active |

## Sport Data Format

### Sport Data Packet

When requesting sport data with `<WB_6>`, the bike responds with:

```
<W6_[SYNC],[UNKNOWN],[POWER],[PULSE],[LEVEL],[DISTANCE],[RPM],[UNKNOWN]>
```
| Field      | Position | Length (Chars) | Description                  |
|------------|----------|----------------|------------------------------|
| `W6_`      | 0-3      | 4              | Header                       |
| `SYNC`     | 4        | 1              | Incrementing counter       |
| `DISTANCE`  | 5-7      | 3              | Distance counter (Needs to be converted and handle overflow) |
| `RPM`    | 8-10     | 3              | Cadence       |
| `PULSE`    | 11-13    | 3              |  User BPM  |
| `LEVEL`    | 14-15    | 2              | Current resistance level        |
| `CALORIES` | 16-21    | 6              | Estimated burned calories        |
| `POWER`      | 22-24    | 3              | Output Power (W)    |
| `UNKNOWN`  | 25-26    | 2              |                              |

### Data Parsing

The app processes sport data with these conversions:

**Distance Calculation:**
```
if old_raw_dist > raw_dist
    Hi_Dist_Value ++ 
old_raw_dist = raw_dist

full_dist = Hi_Dist_Value*1000 + raw_dist

conv_distance = (diameter * full_dist * 3.14 * 2.54) / 100000

```

**Calories:**
```
f_cal = raw_calories / 100
```

**Speed:**

No speed information is available, in the app, speed is derived by :

```
f_speed = rpm * 55 * 0.00478536
```


**Diameter Parsing**

```
diameter = raw / 100
```

**Address parsing**
The data received via EA_[HEX] is 6 bytes long it's the MAC address of the device

### Stored Data

After parsing, the following fields are updated in `IMClass`:

| Field | Type | Description |
|-------|------|-------------|
| `sport_dist` | String | Distance (km or miles) |
| `sport_cal` | String | Calories |
| `sport_rpm` | String | RPM |
| `sport_pulse` | String | Heart rate |
| `sport_speed` | String | Speed |
| `sport_watt` | String | Power (watts) |

## Connection Flow

### 1. Initial Connection

```
1. App connects to 169.254.1.1:1971 (or 196.254.1.1:1971)
2. Send: <EQ_> (start initialization)
3. Receive: <EQ>
4. Receive: <EP_SUPERWIGH> (password)
5. Send: <EP_OK>
6. Receive: <ER_1-20> (min-max resistance)
7. Send: <ER_OK>
8. Receive: <EA_2100> (wheel diameter ×100 = 21.00")
9. Send: <EA_OK>
10. Receive: <ED_00:11:22:33:44:55> (MAC)
11. Send: <ED_OK>
12. Receive: <EM> (memory data)
13. Send: <EM_OK>
14. Receive: <Ez> (init complete)
15. Send: <Ez_OK>, then <CP_300> (pause)
16. Init complete, ready for sport mode
```

### 2. Start Sport Mode

```
1. App sends: <WB_6> (request sport data)
2. Bike responds: <W6_[DATA]>
3. App sends: <W6_OK>
4. App sends: <CP_000> (start)
5. Sport data updates every ~200ms
```

### 3. Change Resistance Level

```
App sends: <CR_10> (set to level 10)
```

Level must be 2 digits, zero-padded (00-99).

### 4. Pause Sport

```
App sends: <CP_300>
Bike stops sending real-time data
```

### 5. Resume Sport

```
App sends: <WB_6>
App sends: <CP_000>
Data resumes
```

### 6. Clear Data

```
App sends: <CC_>
Resets distance counter to 0
```

## Access Point Mode

### Switch to AP Mode

```
1. User initiates AP mode from UI (Needs to be connected in P2P mode)
2. App sets protocol status to PROTOCOL_TOAP (3)
3. App sends: <AS_[SSID]>
4. Bike responds: <AS>
5. App sends: <AK_[PASSWORD]>
6. Bike responds: <AK>
7. App sends: <AP_>
8. Bike responds: <AP>
9. MCU switches to AP mode (Will connect to the registered network)
```

### Variable Storage

AP settings are stored in `Variable` class:

| Variable | Default | Description |
|----------|---------|-------------|
| `APNAME` | `""` | Access Point SSID |
| `APPass` | `""` | Access Point password |
| `APConnect` | `0` | AP connection type |
| `IP` | `"192;168;1;1"` | Custom IP (semicolon-separated) |

## Sending Commands

### From App

Commands are sent via `ConnectedThread.write(byte[])`:
1. Add to message queue (`Protocol_iSpuer.MsgPool`)
2. Timer sends messages every 200ms via `WifiService$SendMSG`
3. Message converted to bytes using ASCII encoding
4. Written to socket output stream

### From Bike

1. `ConnectedThread` reads 60-byte buffer
2. Convert to ASCII string
3. Split by `>` delimiter
4. First part passed to `Protocol_iSpuer.ParserInputMsg()`
5. Parse command and update data

## Error Handling

### Communication Timeout

- `CheckconnecCounter()` increments with each sent message
- After 30 messages without response, connection is terminated
- `communtCounter` reset to 0 on successful receive

### Connection Errors

| Error | Action |
|-------|--------|
| UnknownHostException | Log "unknow host", close socket |
| SocketException | Log "socket not find", close socket |
| IOException | Log "wifi error", close socket |
| Read timeout | Close connection, trigger reconnect |

### Device Errors

| Error Type | Value | Description |
|------------|-------|-------------|
| `ERROR_NONE` | 0 | No error |
| `ERROR_PRODUCER` | 1 | Authentication failed (wrong password) |

## Example Python Implementation

```python
import socket
import time

class ISuperBike:
    DEFAULT_IP = "196.254.1.1"
    FALLBACK_IP = "169.254.1.1"
    PORT = 1971
    TIMEOUT = 2.0
    POLL_INTERVAL = 0.2

    def __init__(self, ip=None):
        self.ip = ip or self.DEFAULT_IP
        self.socket = None
        self.connected = False

        # Data fields
        self.distance = 0.0
        self.rpm = 0
        self.heart_rate = 0
        self.level = 0
        self.calories = 0.0
        self.watts = 0
        self.speed = 0.0

        # Device info
        self.resistance_min = 0
        self.resistance_max = 0
        self.wheel_diameter = 0.0
        self.mac_address = ""

    def connect(self):
        """Connect to the bike"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.TIMEOUT)
            self.socket.connect((self.ip, self.PORT))
            self.connected = True
            print(f"Connected to {self.ip}:{self.PORT}")
            return True
        except (socket.timeout, ConnectionError) as e:
            print(f"Connection failed: {e}")
            return False

    def send(self, command):
        """Send a command to the bike"""
        if not self.connected or not self.socket:
            return False
        try:
            self.socket.send(command.encode('ascii'))
            return True
        except Exception as e:
            print(f"Send error: {e}")
            return False

    def receive(self, timeout=1.0):
        """Receive data from bike"""
        if not self.connected or not self.socket:
            return None
        try:
            self.socket.settimeout(timeout)
            data = self.socket.recv(60)
            return data.decode('ascii', errors='ignore')
        except socket.timeout:
            return None
        except Exception as e:
            print(f"Receive error: {e}")
            return None

    def initialize(self):
        """Initialize the connection with the bike"""
        print("Starting initialization...")

        # Start init
        self.send("<EQ_>")
        resp = self.receive()
        if not resp or "<EQ>" not in resp:
            print("Init failed: no EQ response")
            return False
        print("Init started")

        # Password
        resp = self.receive(timeout=5.0)
        if "<EP_SUPERWIGH>" in resp:
            print("Password received: SUPERWIGH")
            self.send("<EP_OK>")
        else:
            print("Warning: Unexpected password")

        # Range
        resp = self.receive()
        if "<ER_" in resp:
            parts = resp.split("_")
            if "-" in parts[1]:
                r_min, r_max = parts[1].split("-")
                self.resistance_min = int(r_min)
                self.resistance_max = int(r_max)
                print(f"Resistance range: {self.resistance_min}-{self.resistance_max}")
            self.send("<ER_OK>")

        # Diameter
        resp = self.receive()
        if "<EA_" in resp:
            diam = float(resp.split("_")[1].split(">")[0]) / 100.0
            self.wheel_diameter = diam
            print(f"Wheel diameter: {diam:.2f}\"")
            self.send("<EA_OK>")

        # MAC
        resp = self.receive()
        if "<ED_" in resp:
            mac = resp.split("_")[1].split(">")[0]
            self.mac_address = mac
            print(f"MAC: {mac}")
            self.send("<ED_OK>")

        # Memory
        resp = self.receive()
        if "<EM>" in resp:
            print("Memory data received")
            self.send("<EM_OK>")

        # End init
        resp = self.receive()
        if "<Ez>" in resp:
            print("Init complete")
            self.send("<Ez_OK>")
            self.send("<CP_300>")  # Pause after init
            return True

        return False

    def start_sport(self):
        """Start sport mode"""
        self.send("<WB_6>")
        self.send("<CP_000>")
        print("Sport mode started")

    def pause_sport(self):
        """Pause sport"""
        self.send("<CP_300>")
        print("Sport paused")

    def set_level(self, level):
        """Set resistance level (0-99)"""
        cmd = f"<CR_{level:02d}>"
        self.send(cmd)
        print(f"Level set to {level}")

    def clear_data(self):
        """Clear all data"""
        self.send("<CC_>")
        self.distance = 0.0
        print("Data cleared")

    def update_data(self):
        """Update sport data from bike"""
        self.send("<WB_6>")
        resp = self.receive()
        if resp and "<W6_" in resp:
            # Parse: <W6_DIST_RPM_PULSE_LEVEL_CAL_WATT>
            data = resp.split("_")
            if len(data) >= 7:
                self.distance = float(data[1][:4]) / 100.0
                self.rpm = int(data[2][:4])
                self.heart_rate = int(data[3][:4])
                self.level = int(data[4][:3])
                self.calories = float(data[5][:7]) / 100.0
                self.watts = int(data[6][:5])
                self.speed = self.rpm * 55 * 0.009

                # Send ack
                self.send("<W6_OK>")
                return True
        return False

    def disconnect(self):
        """Disconnect from the bike"""
        if self.socket:
            self.send("<AT_>")
            self.socket.close()
            self.connected = False
            print("Disconnected")

    def print_status(self):
        """Print current bike status"""
        print(f"\n=== Bike Status ===")
        print(f"Distance: {self.distance:.2f}")
        print(f"Speed: {self.speed:.1f}")
        print(f"RPM: {self.rpm}")
        print(f"Heart Rate: {self.heart_rate}")
        print(f"Level: {self.level}")
        print(f"Calories: {self.calories:.2f}")
        print(f"Watts: {self.watts}")
        print("=====================\n")


# Example usage
if __name__ == "__main__":
    bike = ISuperBike()

    if bike.connect():
        if bike.initialize():
            bike.print_status()
            bike.start_sport()

            # Main loop
            try:
                for i in range(30):
                    bike.update_data()
                    bike.print_status()

                    # Change level after 5 seconds
                    if i == 5:
                        bike.set_level(5)
                    if i == 15:
                        bike.set_level(10)

                    time.sleep(bike.POLL_INTERVAL)
            except KeyboardInterrupt:
                print("\nStopping...")

            bike.pause_sport()
            bike.disconnect()
```

## Additional Notes

### Distance Wrap-Around

The bike's distance counter has a wrap-around issue. The app tracks this with `Hi_Dist_Value`:
- When `current_distance < old_distance`, `Hi_Dist_Value` increments
- Final distance = `raw_distance + (Hi_Dist_Value * 1000)`

### Level Range

The device reports minimum and maximum resistance levels during initialization. The app should constrain level changes to this range.

### Authentication

The bike authenticates with the password `"SUPERWIGH"`. This appears to be a hardcoded value in the protocol.

## File References

| File | Description |
|------|-------------|
| [smali/protocol/Protocol_iSpuer.smali](smali/protocol/Protocol_iSpuer.smali) | Protocol command handling |
| [smali/protocol/WifiService.smali](smali/protocol/WifiService.smali) | WiFi connection service |
| [smali/protocol/WifiService$ConnectThread.smali](smali/protocol/WifiService$ConnectThread.smali) | Connection thread |
| [smali/protocol/ConnectedThread.smali](smali/protocol/ConnectedThread.smali) | Data I/O thread |
| [smali/protocol/IMClass.smali](smali/protocol/IMClass.smali) | Connection status and data storage |
| [smali/com/isuper_ii/Variable.smali](smali/com/isuper_ii/Variable.smali) | Global variables |

---

**Document Version:** 1.0
**Analysis Date:** 2026-02-21
**Source:** iSuper Fitness 1.1 APK (decompiled)
