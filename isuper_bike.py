#!/usr/bin/env python3
"""
iSuper Gym Bike Protocol Client
Handles all communication and data parsing for the bike.
"""

import socket
import time
import threading
import csv
import os
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

        # CSV logging
        self.log_dir = "activity_logs"
        self.csv_file = None
        self.csv_writer = None
        self.workout_start_time = None

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
                self.log(
                    f"✓ Diameter (8-byte hex): {self.wheel_diameter:.2f}\"")
                return True

            # Format 2: 16 bytes as little-endian float (first 8 bytes)
            if len(data) == 16 and all(c in '0123456789abcdefABCDEF' for c in data):
                bytes_val = bytes.fromhex(data[:8])
                diameter_times_100 = struct.unpack('<f', bytes_val)[0]
                self.wheel_diameter = diameter_times_100
                self.log(
                    f"✓ Diameter (16-byte hex): {self.wheel_diameter:.2f}\"")
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
                        self.log(
                            f"✓ Diameter (EA_hex): {self.wheel_diameter:.2f}\"")
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
        self.log(f"Received: {clean_cmd}")

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

        elif cmd == "ER" and "-" in data:
            parts = data.split("-")
            self.resistance_min = int(parts[0])
            self.resistance_max = int(parts[1])
            self.log(
                f"✓ Resistance: {self.resistance_min}-{self.resistance_max}")
            return "resistance"

        elif cmd == "ER" and data == "OK":
            return "resistance_ack"

        # According to protocol: EA sends MAC address (6 bytes hex), ED sends diameter
        elif cmd == "EA" and data:
            # EA sends MAC address (6 bytes hex according to protocol)
            if len(data) >= 12 and all(c in '0123456789abcdefABCDEF' for c in data):
                # Format as MAC address XX:XX:XX:XX:XX:XX
                mac_bytes = [data[i:i+2] for i in range(0, 12, 2)]
                self.mac_address = ":".join(mac_bytes).upper()
                self.log(f"✓ MAC: {self.mac_address}")
            else:
                self.log("Empty EA message, ignoring...")
            return "mac"

        elif cmd == "EA" and data == "OK":
            return "ea_ok"

        # ED sends wheel diameter according to protocol (diameter / 100)
        elif cmd == "ED" and data:
            try:
                # Try to parse as decimal (diameter × 100)
                if data.isdigit():
                    self.wheel_diameter = int(data) / 100.0
                    self.log(
                        f"✓ Diameter (decimal): {self.wheel_diameter:.2f}\"")
                    return "diameter"
                else:
                    self.log(f"✓ ED data: {data}")
                    return "ed_data"
            except Exception as e:
                self.log(f"! ED parse error: {e}")
                return "ed_error"

        elif cmd == "ED" and data == "OK":
            return "ed_ok"

        elif cmd == "EM" and data:
            try:
                self.memory_data = int(data) if data.isdigit() else data
                self.log(f"✓ Memory: {self.memory_data}")
            except:
                self.log(f"✓ Memory: {data}")
            return "memory"

        elif cmd == "EM" and data == "OK":
            return "memory_ack"

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
        """Parse sport data - Format: <W6_SYNC,DISTANCE,RPM,PULSE,LEVEL,CALORIES,POWER,UNKNOWN>"""
        try:
            # W6_SYNC,DISTANCE,RPM,PULSE,LEVEL,CALORIES,POWER,UNKNOWN
            # Example: <W6_0,224,000,000,03,000000,000,00>
            parts = command.replace("<", "").replace(">", "").split("_")

            if len(parts) < 2:
                self.log(f"! Invalid sport data format: {command}")
                return False

            data_parts = parts[1].split(",")

            # According to protocol, we need at least 8 fields
            # SYNC (position 0) - sync/counter
            if len(data_parts) >= 1:
                self.sync = int(
                    data_parts[0]) if data_parts[0].isdigit() else 0

            # DISTANCE (position 1) - distance counter (3 chars, needs wrap-around handling)
            if len(data_parts) >= 2:
                try:
                    raw_dist = int(data_parts[1].ljust(3, '0'))

                    # Handle wrap-around: if current distance is less than previous, increment hi_dist_value
                    if hasattr(self, 'old_distance') and raw_dist < self.old_distance:
                        self.hi_dist_value += 1
                        self.log(
                            f"⚠ Distance wrap-around detected, hi_dist_value = {self.hi_dist_value}")

                    self.old_distance = raw_dist
                    full_dist = self.hi_dist_value * 1000 + raw_dist

                    # Convert to km/miles using wheel diameter
                    # conv_distance = (diameter * full_dist * 3.14 * 2.54) / 100000
                    self.distance = (self.wheel_diameter *
                                     full_dist * 3.14159 * 2.54) / 100000
                except Exception as e:
                    self.log(f"! Distance parse error: {e}")

            # RPM (position 2) - cadence (3 chars)
            if len(data_parts) >= 3:
                try:
                    self.rpm = int(data_parts[2].ljust(3, '0'))
                except:
                    pass

            # PULSE (position 3) - heart rate/BPM (3 chars)
            if len(data_parts) >= 4:
                try:
                    self.heart_rate = int(data_parts[3].ljust(3, '0'))
                except:
                    pass

            # LEVEL (position 4) - resistance level (2 chars)
            if len(data_parts) >= 5:
                try:
                    self.level = int(data_parts[4].ljust(2, '0'))
                except:
                    pass

            # CALORIES (position 5) - estimated burned calories (6 chars)
            if len(data_parts) >= 6:
                try:
                    raw_calories = int(data_parts[5].ljust(6, '0'))
                    self.calories = raw_calories / 100.0  # f_cal = raw_calories / 100
                except:
                    pass

            # POWER (position 6) - output power in watts (3 chars)
            if len(data_parts) >= 7:
                try:
                    self.watts = int(data_parts[6].ljust(3, '0'))
                except:
                    pass

            # UNKNOWN (position 7) - unknown field (2 chars)
            # Not used currently

            # Calculate speed from RPM using correct formula: f_speed = rpm * 55 * 0.00478536
            # The formula in the doc shows: rpm * 55 * 0.00478536
            # This converts to: rpm * 0.2631948, or approximately rpm * 0.263
            self.speed = self.rpm * 55 * 0.00478536

            self.log(
                f"✓ Sport - Dist:{self.distance:.3f}km RPM:{self.rpm} HR:{self.heart_rate} Lvl:{self.level} W:{self.watts} S:{self.speed:.1f}km/h Cal:{self.calories:.1f}")

            return True
        except Exception as e:
            self.log(f"! Sport data parse error: {e}")
            return False

    def connect(self, max_retries=2):
        """Connect to bike over TCP with fallback to UDP"""
        self.log(f"Attempting to connect to {self.ip}:{self.PORT}...")

        for attempt in range(max_retries):
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(self.TIMEOUT)
                # self.socket.bind(('192.168.0.31', 0))
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

            # If connection failed and we have retries left, try UDP fallback
            if attempt < max_retries - 1:
                self.log(
                    f"Attempting UDP fallback (attempt {attempt + 1}/{max_retries})...")
                try:
                    # Send SUPERWIGH via UDP to potentially wake/authenticate the device
                    udp_socket = socket.socket(
                        socket.AF_INET, socket.SOCK_DGRAM)
                    udp_socket.settimeout(1.0)
                    message = "SUPERWIGH"
                    udp_socket.sendto(message.encode(
                        'ascii'), ('<broadcast>', self.PORT))
                    self.log(
                        f"Broadcast '{message}' via UDP")
                    udp_socket.close()

                    # Wait a moment before retrying TCP
                    time.sleep(0.5)
                except Exception as e:
                    self.log(f"UDP fallback error: {e}")

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
        """Initialize connection with bike following protocol sequence"""
        self.log("=== Starting Initialization ===")

        # Send init command
        if not self.send("<EQ_>"):
            return False

        time.sleep(0.5)

        # Receive loop with timeout
        init_done = False
        for i in range(10):  # 50 iterations = ~10 seconds

            responses = self.receive(timeout=2.0)
            if not responses:
                self.log("Timeout waiting for responses...")
                continue

            for response in responses:
                result = self.parse_command(response)

                # Protocol sequence:
                # 1. <EQ> - init acknowledged (handled in parse_command)
                # 2. <EP_SUPERWIGH> - password
                if result == "password":
                    self.send("<EP_OK>")
                    time.sleep(0.1)
                # 3. <ER_1-20> - resistance range (min-max)
                elif result == "resistance":
                    self.send("<ER_OK>")
                    time.sleep(0.5)
                # 4. <EA_...> - MAC address (according to protocol)
                elif result == "mac":
                    self.send("<EA_OK>")
                    time.sleep(0.1)
                # 5. <ED_2100> - wheel diameter ×100 (21.00")
                elif result == "diameter":
                    self.send("<ED_OK>")
                    time.sleep(0.1)
                # 6. <EM> - memory data
                elif result == "memory":
                    self.send("<EM_OK>")
                    time.sleep(0.1)
                # Optional: <ET_Upright> or <EV> - equipment type/vendor
                elif result in ["et_data", "ev_data"]:
                    self.send("<ET_OK>")
                    time.sleep(0.1)
                # 7. <Ez> - end of init phase
                elif result == "init_complete":
                    self.send("<Ez_OK>")
                    time.sleep(0.1)
                    self.send("<CP_300>")  # Pause after init

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

    def set_level(self, level, min, max):
        """Set resistance level (0-99)"""
        if level < min:
            level = min
        if level > max:
            level = max
        level -= 1  # CR_00 => Level 1
        if level < 0:
            level = 0
        cmd = f"<CR_{level:02d}>"
        self.send(cmd)
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

    def start_logging(self, program_name="manual"):
        """Start CSV logging for workout"""
        # Create log directory if it doesn't exist
        os.makedirs(self.log_dir, exist_ok=True)

        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.log_dir}/workout_{timestamp}_{program_name}.csv"

        try:
            self.csv_file = open(filename, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)

            # Write header
            self.csv_writer.writerow([
                'timestamp',
                'elapsed_seconds',
                'distance_km',
                'speed_kmh',
                'rpm',
                'heart_rate_bpm',
                'level',
                'calories_kcal',
                'watts'
            ])

            self.workout_start_time = datetime.now()
            self.log(f"Started logging to {filename}")
            return True
        except Exception as e:
            self.log(f"Error starting CSV log: {e}")
            return False

    def log_data(self):
        """Log current data to CSV"""
        if not self.csv_writer or not self.workout_start_time:
            return

        try:
            elapsed = (datetime.now() -
                       self.workout_start_time).total_seconds()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.csv_writer.writerow([
                timestamp,
                f"{elapsed:.2f}",
                f"{self.distance:.3f}",
                f"{self.speed:.1f}",
                self.rpm,
                self.heart_rate,
                self.level,
                f"{self.calories:.1f}",
                self.watts
            ])
            self.csv_file.flush()
        except Exception as e:
            self.log(f"Error logging data: {e}")

    def stop_logging(self):
        """Stop CSV logging"""
        if self.csv_file:
            try:
                self.csv_file.close()
                self.log("CSV logging stopped")
            except:
                pass
            finally:
                self.csv_file = None
                self.csv_writer = None
                self.workout_start_time = None

    def configure_ap(self, ssid, password):
        """Configure bike to connect to WiFi network in AP mode"""
        print(f"Configuring AP mode for SSID: {ssid}")

        # Send SSID
        ssid_cmd = f"<AS_{ssid}>"
        self.send(ssid_cmd)
        resp = self.receive(timeout=2.0)

        if resp and "<AS>" in resp:
            print("SSID acknowledged")
        else:
            print("Warning: SSID not acknowledged")

        # Send password
        pwd_cmd = f"<AK_{password}>"
        self.send(pwd_cmd)
        resp = self.receive(timeout=2.0)

        if resp and "<AK>" in resp:
            print("Password acknowledged")
        else:
            print("Warning: Password not acknowledged")

        # Trigger AP mode switch
        self.send("<AP_>")
        resp = self.receive(timeout=5.0)

        if resp and "<AP>" in resp:
            print("AP mode activated successfully!")
            print("\n=== IMPORTANT ===")
            print("The bike is now switching to AP mode.")
            print("Please switch your device WiFi to connect to: " + ssid)
            print("Then run the dashboard with your local network IP.")
            print("==================\n")
            return True
        else:
            print("Error: AP mode activation failed")
            return False
