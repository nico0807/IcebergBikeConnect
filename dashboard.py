#!/usr/bin/env python3
"""
iSuper Gym Bike Dashboard - AP Mode
Terminal UI for displaying real-time sport data.
"""

import curses
import time
import socket
import math
from isuper_bike import ISuperBike


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
                self.stdscr.addch(y, x + i, curses.ACS_HLINE,
                                  curses.color_pair(6))
            self.stdscr.addch(y, x + width - 1,
                              curses.ACS_URCORNER, curses.color_pair(6))
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
                self.stdscr.addch(y + row, x, curses.ACS_VLINE,
                                  curses.color_pair(6))
                self.stdscr.addch(y + row, x + width - 1,
                                  curses.ACS_VLINE, curses.color_pair(6))
            except:
                pass

        # Bottom border
        try:
            self.stdscr.addch(y + height - 1, x,
                              curses.ACS_LLCORNER, curses.color_pair(6))
            for i in range(1, width - 1):
                self.stdscr.addch(y + height - 1, x + i,
                                  curses.ACS_HLINE, curses.color_pair(6))
            self.stdscr.addch(y + height - 1, x + width - 1,
                              curses.ACS_LRCORNER, curses.color_pair(6))
        except:
            pass

    def draw_gauge(self, y, x, width, value, max_value, label="", color=2):
        """Draw a horizontal gauge/bar"""
        bar_width = width - 10
        fill = min(int((value / max_value) * bar_width)
                   if max_value > 0 else 0, bar_width)

        # Label
        self.stdscr.addstr(y, x, f"{label}", curses.color_pair(6))
        self.stdscr.addstr(
            y, x + 8, f"{value:6.1f}/{max_value}", curses.color_pair(2))

        # Bar
        bar_y = y + 1
        for i in range(bar_width):
            if i < fill:
                try:
                    self.stdscr.addch(
                        bar_y, x + 8 + i, curses.ACS_CKBOARD, curses.color_pair(color))
                except:
                    self.stdscr.addstr(bar_y, x + 8 + i, " ",
                                       curses.color_pair(color))
            else:
                self.stdscr.addstr(bar_y, x + 8 + i, " ", curses.color_pair(6))

        return bar_y + 2

    def draw_dial(self, y, x, size, value, max_value, label=""):
        """Draw a simple dial/gauge"""
        radius = size // 2
        center_y, center_x = y + radius, x + radius

        # Label
        try:
            self.stdscr.addstr(y + size, x + size // 2 -
                               len(label) // 2, label, curses.color_pair(2))
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
                    self.stdscr.addch(cy, cx, curses.ACS_PLUS,
                                      curses.color_pair(6))
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
                    self.stdscr.addch(
                        cy, cx, curses.ACS_DIAMOND, curses.color_pair(3))
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
            self.stdscr.addstr(0, (width - len(header)) // 2,
                               header, curses.color_pair(1) | curses.A_BOLD)
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
            if status['rpm'] > 100:
                color = 3
            if status['rpm'] > 120:
                color = 4
            self.stdscr.addstr(rpm_y, rpm_x, f"{status['rpm']:6d}",
                               curses.color_pair(color) | curses.A_BOLD)
        except:
            pass

        # Heart rate box
        self.draw_box(data_y, 2 + col_width * 2, 6,
                      col_width, "HEART RATE (bpm)")
        hr_y = data_y + 2
        hr_x = 2 + col_width * 2 + col_width // 2 - 4
        try:
            color = 2
            if status['heart_rate'] > 120:
                color = 3
            if status['heart_rate'] > 150:
                color = 4
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
        self.draw_box(dist_cal_y, 2 + col_width, 4,
                      col_width, "CALORIES (kcal)")
        cal_y = dist_cal_y + 2
        cal_x = 2 + col_width + col_width // 2 - 5
        try:
            self.stdscr.addstr(cal_y, cal_x, f"{status['calories']:8.1f}",
                               curses.color_pair(5) | curses.A_BOLD)
        except:
            pass

        # Watts
        self.draw_box(dist_cal_y, 2 + col_width * 2,
                      4, col_width, "POWER (Watts)")
        watt_y = dist_cal_y + 2
        watt_x = 2 + col_width * 2 + col_width // 2 - 4
        try:
            color = 2
            if status['watts'] > 150:
                color = 3
            if status['watts'] > 200:
                color = 4
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
                    self.bike.set_level(
                        self.bike.level + 1, self.bike.resistance_min, self.bike.resistance_max)
            elif key == curses.KEY_DOWN:
                if self.bike:
                    self.bike.set_level(
                        self.bike.level - 1, self.bike.resistance_min, self.bike.resistance_max)

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


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='iSuper Bike Dashboard - AP Mode')
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
                # Fixed port from 1963 to 1971
                result = s.connect_ex((ip, 1971))
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
        curses.wrapper(lambda stdscr: Dashboard(
            stdscr).run(args.ip, args.debug))
    except KeyboardInterrupt:
        print("\nDashboard stopped by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
