#!/usr/bin/env python3
"""
iSuper Gym Bike Dashboard - AP Mode
Connects to the bike and displays real-time sport data in a terminal dashboard.
"""

import socket
import time
import curses
import threading
import sys
from datetime import datetime

class ISuperBike:
    """iSuper Bike Protocol Client"""

    # AP Mode Connection Settings
    DEFAULT_IP = "169.254.1.1"  # User's IP (was "192.168.4.1")
    FALLBACK_IP = "169.254.1.1"
    PORT = 1971
    TIMEOUT = 3.0
    POLL_INTERVAL = 0.2

    def __init__(self, ip=None, debug=False):
        self.ip = ip or self.DEFAULT_IP
        self.socket = None
        self.connected = False
        self.initialized = False
        self.debug = debug
        self.running = False
        self.lock = threading.Lock()

        # Sport data
        self.distance = 0.0
        self.rpm = 0
        self.heart_rate = 0
        self.level = 0
        self.calories = 0.0
        self.watts = 0
        self.speed = 0.0

        # Device info
        self.password = None
        self.resistance_min = 0
        self.resistance_max = 0
        self.wheel_diameter = 21.0  # Default fallback
        self.mac_address = ""
        self.unit_type = "M"  # Default metric
        self.memory_data = None

        # Stats
        self.last_update = None
        self.messages_sent = 0
        self.messages_received = 0

        # Distance tracking for wrap-around
        self.old_distance = 0.0
        self.hi_dist_value = 0

    def log(self, message):
        """Debug logging"""
        if self.debug:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {message}")

    def parse_wheel_diameter_hex(self, hex_data):
        """Parse wheel diameter from hex like '20f85e21fea8'"""
        import struct

        try:
            # Clean the hex data
            data = hex_data.strip()

            # Try different formats:
            # Format 1: 8 bytes as little-endian float
            if len(data) == 8 and all(c in '0123456789abcdefABCDEF' for c in data):
                bytes_val = bytes.fromhex(data)
                diameter_times_100 = struct.unpack('<f', bytes_val)[0]
                self.wheel_diameter = diameter_times_100
                self.log(f"✓ Diameter (8-byte hex): {self.wheel_diameter:.2f}\"")
                return True

            # Format 2: 16 bytes as little-endian float (first 8 bytes)
            if len(data) == 16 and all(c in '0123456789abcdefABCDEF' for c in data):
                bytes_val = bytes.fromhex(data[:8])
                diameter_times_100 = struct.unpack('<f', bytes_val)[0]
                self.wheel_diameter = diameter_times_100
                self.log(f"✓ Diameter (16-byte hex): {self.wheel_diameter:.2f}\"")
                return True

            # Format 3: Try as decimal × 100
            if data.isdigit():
                self.wheel_diameter = int(data) / 100.0
                self.log(f"✓ Diameter (decimal): {self.wheel_diameter:.2f}\"")
                return True

            # Format 4: Try parsing differently - look for _EA_<hex>
            if hex_data.startswith("EA_") and "_" in hex_data:
                parts = hex_data.split("_")
                if len(parts) >= 2 and len(parts[1]) >= 8:
                    hex_val = parts[1]
                    if all(c in '0123456789abcdefABCDEF' for c in hex_val):
                        bytes_val = bytes.fromhex(hex_val)
                        diameter_times_100 = struct.unpack('<f', bytes_val)[0]
                        self.wheel_diameter = diameter_times_100
                        self.log(f"✓ Diameter (EA_hex): {self.wheel_diameter:.2f}\"")
                        return True
            self.wheel_diameter = 21
            return True

        except Exception as e:
            self.log(f"! Error parsing diameter: {e}")
            # Keep default
            return False

    def parse_command(self, command):
        """Parse a single command - simplified"""
        if not command:
            return None

        # Remove < and >
        clean_cmd = command.replace("<", "").replace(">", "")
        print(clean_cmd)
        # Check if this is just EA_ (command without data part)
        if clean_cmd == "EA":
            self.log("⏳ EA without data, waiting...")
            return "wait_for_data"

        if clean_cmd.startswith("EA"):
            clean_cmd = clean_cmd.replace("\r\n", "")

        # Split by _ to get command and data
        parts = clean_cmd.split("_")

        if len(parts) == 1:
            cmd = parts[0]
            data = None
        else:
            cmd = parts[0]
            data = "_".join(parts[1:])

        # Handle based on command
        if cmd == "EQ" and data == "OK":
            self.log("✓ Init acknowledged")
            return "init_ack"

        elif cmd == "EP" and data == "SUPERWIGH":
            self.password = "SUPERWIGH"
            self.log("✓ Password: SUPERWIGH")
            return "password"

        elif cmd == "EP" and data == "OK":
            return "password_ack"

        elif cmd == "ET" and data:
            if data == "OK":
                return "et_ack"
            else:
                self.log(f"✓ ET data: {data}")
                return "et_data"

        elif cmd == "EM" and data:
            try:
                self.memory_data = int(data) if data.isdigit() else data
                self.log(f"✓ Memory: {self.memory_data}")
            except:
                self.log(f"✓ Memory: {data}")
            return "memory"

        elif cmd == "EM" and data == "OK":
            return "memory_ack"

        elif cmd == "ER" and "-" in data:
            parts = data.split("-")
            self.resistance_min = int(parts[0])
            self.resistance_max = int(parts[1])
            self.log(f"✓ Resistance: {self.resistance_min}-{self.resistance_max}")
            return "resistance"

        elif cmd == "ER" and data == "OK":
            return "resistance_ack"

        elif cmd == "EA" and data:
            if self.parse_wheel_diameter_hex(data):
                return "diameter"
            return "diameter_ack"

        elif cmd == "EA" and data == "OK":
            return "diameter_ack"

        elif cmd == "ED" and data:
            self.mac_address = data
            self.log(f"✓ MAC/IP: {self.mac_address}")
            return "mac"

        elif cmd == "ED" and data == "OK":
            return "mac_ack"

        elif cmd == "EU" and data:
            self.unit_type = data
            self.log(f"✓ Unit: {self.unit_type}")
            return "unit"

        elif cmd == "EU" and data == "OK":
            return "unit_ack"

        elif cmd == "EV" and data:
            self.log(f"✓ EV: {data}")
            return "ev_data"

        elif cmd == "EV" and data == "OK":
            return "ev_ack"

        elif cmd == "Ez" and ("1E" in data or "OK" in data):
            self.log("✓ Init complete")
            return "init_complete"

        elif cmd == "Ez" and data == "OK":
            return "init_complete_ack"

        elif cmd.startswith("W6"):
            self.parse_sport_data(command)
            return "sport_data"

        elif cmd == "W6" and data == "OK":
            return "sport_ack"

        elif cmd == "CP" and data == "OK":
            return "cp_ack"

        elif cmd == "CP" and data == "300":
            return "cp_pause"

        elif cmd == "CP" and data == "000":
            return "cp_start"

        else:
            self.log(f"? Unknown: {cmd}")
            return "unknown"

    def parse_sport_data(self, command):
        """Parse sport data - Format: W6_SYNC,NERGY,POW,BPM,LEVEL,DIST,RPM,?"""
        try:
            # W6_SYNC,NERGY,POW,BPM,LEVEL,DIST,RPM,?
            # Example: W6_8,039,000,000,03,000224,000,25
            parts = command.replace("<", "").replace(">", "").split("_")
            parts = parts[1].split(",")
            if len(parts) >= 7:
                # SYNC (part 1) - sync/counter
                self.sync = int(parts[0]) if parts[0].isdigit() else 0

                # NERGY (part 2) - energy/calories in some format
                try:
                    self.watts = int(parts[1].ljust(4, '0'))
                except:
                    pass

                # POW (part 3) - power/watts
                try:
                    self.watts = int(parts[2].ljust(4, '0'))
                except:
                    pass

                # BPM (part 4) - heart rate
                try:
                    self.heart_rate = int(parts[3].ljust(4, '0'))
                except:
                    pass

                # LEVEL (part 5) - resistance level
                try:
                    self.level = int(parts[4].ljust(3, '0'))
                except:
                    pass

                # DIST (part 6) - distance
                try:
                    dist_data = parts[5].ljust(6, '0')
                    raw_dist = float(dist_data) / 1000.0
                    self.distance = raw_dist * self.wheel_diameter * 3.14 * 2.54 / 100000
                except:
                    pass

                # RPM (part 7) - cadence
                try:
                    self.rpm = int(parts[6].ljust(4, '0'))
                except:
                    pass

                # Calculate speed from RPM
                self.speed = self.rpm * 55 * 0.009

                self.log(f"✓ Sport - Dist:{self.distance:.2f}km RPM:{self.rpm} HR:{self.heart_rate} Lvl:{self.level} W:{self.watts}W S:{self.speed:.1f}km/h")
        except Exception as e:
            self.log(f"! Sport data parse error: {e}")

    def connect(self):
        """Connect to bike over TCP"""
        self.log(f"Attempting to connect to {self.ip}:{self.PORT}...")
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.TIMEOUT)
            self.socket.connect((self.ip, self.PORT))
            self.connected = True
            self.log(f"Connected successfully to {self.ip}:{self.PORT}")
            return True
        except socket.timeout:
            self.log(f"Connection timeout to {self.ip}")
        except ConnectionRefusedError:
            self.log(f"Connection refused by {self.ip}")
        except socket.gaierror:
            self.log(f"DNS error: unable to resolve {self.ip}")
        except Exception as e:
            self.log(f"Connection error: {e}")
        return False

    def disconnect(self):
        """Disconnect from bike"""
        self.running = False
        if self.socket:
            try:
                self.send("<AT_>")
                self.socket.close()
            except:
                pass
        self.connected = False
        self.log("Disconnected")

    def send(self, command):
        """Send command to bike"""
        if not self.connected or not self.socket:
            return False
        try:
            self.socket.send(command.encode('ascii'))
            self.messages_sent += 1
            self.log(f"Sent: {command}")
            return True
        except Exception as e:
            self.log(f"Send error: {e}")
            self.connected = False
            return False

    def receive(self, timeout=1.0):
        """Receive data with buffering to handle split responses"""
        if not self.connected or not self.socket:
            return None
        try:
            self.socket.settimeout(timeout)
            data = self.socket.recv(1024)
            if data:
                decoded = data.decode('ascii', errors='ignore')
                # Split by > delimiter to get individual commands
                commands = decoded.replace(">", "\n<").strip().split("\n<")
                # Filter out empty commands and add > to each valid command
                commands = [cmd + ">" for cmd in commands if cmd]
                if commands:
                    self.messages_received += 1
                    self.log(f"Received {len(commands)} command(s)")
                return commands
        except socket.timeout:
            return []
        except Exception as e:
            self.log(f"Receive error: {e}")
            self.connected = False
            return []
        return None

    def initialize(self):
        """Initialize connection with bike"""
        self.log("=== Starting Initialization ===")

        # Send init command
        if not self.send("<EQ_>"):
            return False

        time.sleep(0.5)

        # Receive loop with timeout
        init_done = False
        for i in range(50):  # 50 iterations = ~10 seconds

            responses = self.receive(timeout=2.0)
            if not responses:
                self.log("Timeout waiting for responses...")
                continue

            for response in responses:
                result = self.parse_command(response)

                if result == "password":
                    self.send("<EP_OK>")
                    time.sleep(0.1)
                elif result == "resistance":
                    self.send("<ER_OK>")
                    time.sleep(0.5)
                elif result == "diameter":
                    self.send("<EA_OK>")
                    time.sleep(0.1)
                elif result == "mac":
                    self.send("<ED_OK>")
                    time.sleep(0.1)
                elif result == "unit":
                    self.send("<EU_OK>")
                    time.sleep(0.1)
                elif result == "memory":
                    self.send("<EM_OK>")
                    time.sleep(0.1)
                elif result in ["et_data", "ev_data"]:
                    self.send("<ET_OK>")
                    time.sleep(0.1)
                elif result == "init_complete":
                    self.send("<Ez_OK>")
                    time.sleep(0.1)
                    self.send("<CP_300>")  # Pause

                    init_done = True
                    self.log("Init complete")
            if init_done:
                break

        if init_done:
            self.initialized = True
            return True

        self.log("Init incomplete but continuing...")
        self.initialized = True
        return True

    def start_sport(self):
        """Start sport mode"""
        self.log("Starting sport mode...")
        self.send("<WB_6>")
        time.sleep(0.1)
        self.send("<CP_000>")
        self.log("Sport mode active ✓")

    def pause_sport(self):
        """Pause sport"""
        self.log("Pausing sport...")
        self.send("<CP_300>")
        self.log("Sport paused")

    def set_level(self, level):
        """Set resistance level (0-99)"""
        if level < 0:
            level = 0
        if level > 99:
            level = 99
        cmd = f"<CR_{level:02d}>"
        self.send(cmd)
        with self.lock:
            self.level = level
        self.log(f"Level set to {level}")

    def clear_data(self):
        """Clear all data"""
        self.send("<CC_>")
        with self.lock:
            self.distance = 0.0
            self.calories = 0.0
            self.hi_dist_value = 0
            self.old_distance = 0.0
        self.log("Data cleared")

    def update_data(self):
        """Update sport data from bike"""
        if not self.connected:
            return False

        self.send("<WB_6>")
        responses = self.receive(timeout=0.5)

        if responses:
            for response in responses:
                result = self.parse_command(response)

                if result == "sport_data":
                    self.send("<W6_OK>")
                    return True

        return False

    def get_status(self):
        """Get current status dict"""
        with self.lock:
            return {
                'connected': self.connected,
                'initialized': self.initialized,
                'distance': self.distance,
                'speed': self.speed,
                'rpm': self.rpm,
                'heart_rate': self.heart_rate,
                'level': self.level,
                'calories': self.calories,
                'watts': self.watts,
                'last_update': self.last_update,
                'messages_sent': self.messages_sent,
                'messages_received': self.messages_received,
                'resistance_min': self.resistance_min,
                'resistance_max': self.resistance_max,
                'wheel_diameter': self.wheel_diameter,
                'mac_address': self.mac_address,
            }


class Dashboard:
    """Terminal dashboard for bike data"""

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.bike = None
        self.running = True
        self.paused = False
        self.auto_update = True

        # Colors
        curses.start_color()
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLACK)

        # Hide cursor
        curses.curs_set(0)

        # Input timeout
        self.stdscr.timeout(100)

    def draw_box(self, y, x, height, width, title=""):
        """Draw a box using borders"""
        # Top and bottom borders
        try:
            self.stdscr.addch(y, x, curses.ACS_ULCORNER, curses.color_pair(6))
            for i in range(1, width - 1):
                self.stdscr.addch(y, x + i, curses.ACS_HLINE, curses.color_pair(6))
            self.stdscr.addch(y, x + width - 1, curses.ACS_URCORNER, curses.color_pair(6))
        except:
            pass

        # Side borders and title
        if title:
            title_pos = max(1, (width - len(title)) // 2)
            try:
                self.stdscr.addstr(y, title_pos, title, curses.color_pair(2))
            except:
                pass

        for row in range(1, height - 1):
            try:
                self.stdscr.addch(y + row, x, curses.ACS_VLINE, curses.color_pair(6))
                self.stdscr.addch(y + row, x + width - 1, curses.ACS_VLINE, curses.color_pair(6))
            except:
                pass

        # Bottom border
        try:
            self.stdscr.addch(y + height - 1, x, curses.ACS_LLCORNER, curses.color_pair(6))
            for i in range(1, width - 1):
                self.stdscr.addch(y + height - 1, x + i, curses.ACS_HLINE, curses.color_pair(6))
            self.stdscr.addch(y + height - 1, x + width - 1, curses.ACS_LRCORNER, curses.color_pair(6))
        except:
            pass

    def draw_gauge(self, y, x, width, value, max_value, label="", color=2):
        """Draw a horizontal gauge/bar"""
        bar_width = width - 10
        fill = min(int((value / max_value) * bar_width) if max_value > 0 else 0, bar_width)

        # Label
        self.stdscr.addstr(y, x, f"{label}", curses.color_pair(6))
        self.stdscr.addstr(y, x + 8, f"{value:6.1f}/{max_value}", curses.color_pair(2))

        # Bar
        bar_y = y + 1
        for i in range(bar_width):
            if i < fill:
                try:
                    self.stdscr.addch(bar_y, x + 8 + i, curses.ACS_CKBOARD, curses.color_pair(color))
                except:
                    self.stdscr.addstr(bar_y, x + 8 + i, " ", curses.color_pair(color))
            else:
                self.stdscr.addstr(bar_y, x + 8 + i, " ", curses.color_pair(6))

        return bar_y + 2

    def draw_dial(self, y, x, size, value, max_value, label=""):
        """Draw a simple dial/gauge"""
        radius = size // 2
        center_y, center_x = y + radius, x + radius

        # Label
        try:
            self.stdscr.addstr(y + size, x + size // 2 - len(label) // 2, label, curses.color_pair(2))
        except:
            pass

        # Draw circle (simplified)
        for i in range(180):  # Top half circle
            angle = 3.14159 * i / 180
            py = int(radius * 0.8 * (1 - math.cos(angle)))
            px = int(radius * 0.8 * math.sin(angle))

            cy, cx = center_y - py, center_x + px
            if 0 <= cy < self.stdscr.getmaxyx()[0] and 0 <= cx < self.stdscr.getmaxyx()[1]:
                try:
                    self.stdscr.addch(cy, cx, curses.ACS_PLUS, curses.color_pair(6))
                except:
                    pass

        # Needle
        angle = 3.14159 * (value / max_value)
        needle_len = radius * 0.7
        ny = int(needle_len * (1 - math.cos(angle)))
        nx = int(needle_len * math.sin(angle))

        for i in range(1, int(needle_len)):
            t = i / needle_len
            cy, cx = center_y - int(ny * t), center_x + int(nx * t)
            if 0 <= cy < self.stdscr.getmaxyx()[0] and 0 <= cx < self.stdscr.getmaxyx()[1]:
                try:
                    self.stdscr.addch(cy, cx, curses.ACS_DIAMOND, curses.color_pair(3))
                except:
                    pass

        # Value
        val_str = f"{int(value)}"
        try:
            self.stdscr.addstr(center_y + radius // 2, center_x - len(val_str) // 2,
                           val_str, curses.color_pair(3))
        except:
            pass

        return y + size + 2

    def update(self):
        """Update dashboard display"""
        self.stdscr.clear()

        if not self.bike:
            self.draw_no_bike()
            return

        status = self.bike.get_status()
        height, width = self.stdscr.getmaxyx()

        # Header
        header = f" iSuper Bike Dashboard - AP Mode "
        try:
            self.stdscr.addstr(0, (width - len(header)) // 2, header, curses.color_pair(1) | curses.A_BOLD)
        except:
            pass

        # Status line
        status_parts = []
        if status['connected']:
            status_parts.append("CONNECTED")
        else:
            status_parts.append("DISCONNECTED")

        if self.paused:
            status_parts.append("[PAUSED]")
        else:
            status_parts.append("[ACTIVE]")

        if self.auto_update:
            status_parts.append("[AUTO]")
        else:
            status_parts.append("[MANUAL]")

        status_text = "Status: " + " ".join(status_parts)

        try:
            self.stdscr.addstr(2, 2, status_text, curses.color_pair(6))
        except:
            pass

        # Device info
        info_y = 4
        try:
            self.stdscr.addstr(info_y, 2, f"IP: {self.bike.ip} | Port: {self.bike.PORT}",
                           curses.color_pair(6))
            info_y += 1
            self.stdscr.addstr(info_y, 2,
                           f"MAC: {status['mac_address'] or 'N/A'} | "
                           f"Wheel: {status['wheel_diameter']:.2f}\" | "
                           f"Range: {status['resistance_min']}-{status['resistance_max']}",
                           curses.color_pair(6))
            info_y += 1
            self.stdscr.addstr(info_y, 2,
                           f"Sent: {status['messages_sent']} | "
                           f"Recv: {status['messages_received']} | "
                           f"Last Update: {status['last_update'].strftime('%H:%M:%S') if status['last_update'] else 'Never'}",
                           curses.color_pair(6))
        except:
            pass

        # Main data boxes
        data_y = info_y + 2
        col_width = 40

        # Speed box
        self.draw_box(data_y, 2, 6, col_width, "SPEED (km/h)")
        speed_y = data_y + 2
        speed_x = 2 + col_width // 2 - 4
        try:
            self.stdscr.addstr(speed_y, speed_x, f"{status['speed']:6.1f}",
                           curses.color_pair(3) | curses.A_BOLD)
        except:
            pass

        # RPM box
        self.draw_box(data_y, 2 + col_width, 6, col_width, "RPM")
        rpm_y = data_y + 2
        rpm_x = 2 + col_width + col_width // 2 - 4
        try:
            color = 2
            if status['rpm'] > 100: color = 3
            if status['rpm'] > 120: color = 4
            self.stdscr.addstr(rpm_y, rpm_x, f"{status['rpm']:6d}",
                           curses.color_pair(color) | curses.A_BOLD)
        except:
            pass

        # Heart rate box
        self.draw_box(data_y, 2 + col_width * 2, 6, col_width, "HEART RATE (bpm)")
        hr_y = data_y + 2
        hr_x = 2 + col_width * 2 + col_width // 2 - 4
        try:
            color = 2
            if status['heart_rate'] > 120: color = 3
            if status['heart_rate'] > 150: color = 4
            self.stdscr.addstr(hr_y, hr_x, f"{status['heart_rate']:6d}",
                           curses.color_pair(color) | curses.A_BOLD)
        except:
            pass

        # Level box
        self.draw_box(data_y, 2 + col_width * 3, 6, col_width, "LEVEL")
        level_y = data_y + 2
        level_x = 2 + col_width * 3 + col_width // 2 - 4
        try:
            self.stdscr.addstr(level_y, level_x, f"{status['level']:6d}",
                           curses.color_pair(5) | curses.A_BOLD)
        except:
            pass

        # Distance and Calories
        dist_cal_y = data_y + 7

        # Distance
        self.draw_box(dist_cal_y, 2, 4, col_width, "DISTANCE (km)")
        dist_y = dist_cal_y + 2
        dist_x = 2 + col_width // 2 - 5
        try:
            self.stdscr.addstr(dist_y, dist_x, f"{status['distance']:8.3f}",
                           curses.color_pair(1) | curses.A_BOLD)
        except:
            pass

        # Calories
        self.draw_box(dist_cal_y, 2 + col_width, 4, col_width, "CALORIES (kcal)")
        cal_y = dist_cal_y + 2
        cal_x = 2 + col_width + col_width // 2 - 5
        try:
            self.stdscr.addstr(cal_y, cal_x, f"{status['calories']:8.1f}",
                           curses.color_pair(5) | curses.A_BOLD)
        except:
            pass

        # Watts
        self.draw_box(dist_cal_y, 2 + col_width * 2, 4, col_width, "POWER (Watts)")
        watt_y = dist_cal_y + 2
        watt_x = 2 + col_width * 2 + col_width // 2 - 4
        try:
            color = 2
            if status['watts'] > 150: color = 3
            if status['watts'] > 200: color = 4
            self.stdscr.addstr(watt_y, watt_x, f"{status['watts']:6d}",
                           curses.color_pair(color) | curses.A_BOLD)
        except:
            pass

        # Controls help
        help_y = dist_cal_y + 5
        try:
            help_text = (" Controls: [↑/↓] Level | [Space] Pause/Resume | [C] Clear Data | "
                        "[A] Toggle Auto | [Q] Quit | [R] Reconnect ")
            self.stdscr.addstr(help_y, 2, help_text, curses.color_pair(6))
        except:
            pass

        self.stdscr.refresh()

    def draw_no_bike(self):
        """Display when no bike connected"""
        height, width = self.stdscr.getmaxyx()

        try:
            self.stdscr.addstr(height // 2 - 2, width // 2 - 20,
                           "No bike connected", curses.color_pair(4) | curses.A_BOLD)
            self.stdscr.addstr(height // 2, width // 2 - 25,
                           "Press [C] to connect, [Q] to quit", curses.color_pair(6))
        except:
            pass

        self.stdscr.refresh()

    def run(self, ip, debug):
        """Run dashboard main loop"""
        self.bike = ISuperBike(ip, debug)

        # Connect and initialize
        self.stdscr.addstr(0, 2, "Connecting to bike...", curses.color_pair(6))
        self.stdscr.refresh()

        if self.bike.connect():
            time.sleep(0.5)
            if self.bike.initialize():
                time.sleep(0.5)
                self.bike.start_sport()
                self.auto_update = True
            else:
                self.auto_update = False
        else:
            self.auto_update = False

        last_update = time.time()

        while self.running:
            # Handle input
            key = self.stdscr.getch()

            if key == ord('q') or key == ord('Q'):
                break
            elif key == ord('c') or key == ord('C'):
                if not self.bike.connected:
                    self.bike.connect()
                    if self.bike.connected:
                        time.sleep(0.5)
                        self.bike.initialize()
                        time.sleep(0.5)
                        self.bike.start_sport()
                        self.auto_update = True
            elif key == ord('r') or key == ord('R'):
                self.bike.disconnect()
                time.sleep(1)
                self.bike.connect()
                if self.bike.connected:
                    time.sleep(0.5)
                    self.bike.initialize()
                    time.sleep(0.5)
                    self.bike.start_sport()
                    self.auto_update = True
            elif key == ord(' '):  # Space
                if not self.paused:
                    self.bike.pause_sport()
                    self.paused = True
                else:
                    self.bike.start_sport()
                    self.paused = False
            elif key == ord('a') or key == ord('A'):
                self.auto_update = not self.auto_update
            elif key == ord('c') or key == ord('C'):  # Clear - handled above
                pass
            elif key == ord('x'):  # Clear data
                self.bike.clear_data()
            elif key == curses.KEY_UP:
                if self.bike:
                    self.bike.set_level(self.bike.level + 1)
            elif key == curses.KEY_DOWN:
                if self.bike:
                    self.bike.set_level(self.bike.level - 1)

            # Auto-update data
            if self.auto_update and self.bike and self.bike.connected:
                current_time = time.time()
                if current_time - last_update >= self.bike.POLL_INTERVAL:
                    self.bike.update_data()
                    last_update = current_time

            # Update display
            self.update()

        # Cleanup
        self.bike.disconnect()


import math


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='iSuper Bike Dashboard - AP Mode')
    parser.add_argument('--ip', default='169.254.1.1',
                       help='Bike IP address (default: 192.168.1.54)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    parser.add_argument('--list-ips', action='store_true',
                       help='Scan for available bikes on local network')

    args = parser.parse_args()

    # IP scanner
    if args.list_ips:
        print("Scanning for bikes...")
        ips_to_try = [
            "192.168.4.1",  # Common AP IP
            "192.168.1.1",
            "192.168.0.1",
            "196.254.1.1",
            "169.254.1.1",
        ]

        for ip in ips_to_try:
            print(f"Trying {ip}...", end=" ")
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.0)
                result = s.connect_ex((ip, 1971))  # Fixed port from 1963 to 1971
                s.close()
                if result == 0:
                    print(f"FOUND! ✓")
                else:
                    print("not found")
            except Exception as e:
                print(f"error: {e}")
        return

    # Run dashboard
    try:
        curses.wrapper(lambda stdscr: Dashboard(stdscr).run(args.ip, args.debug))
    except KeyboardInterrupt:
        print("\nDashboard stopped by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
