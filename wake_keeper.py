"""
wake_keeper.py — OS-level screen wake lock for the iSuper Bike dashboards.

Used by both dashboard.py (curses) and dashboard_gui.py (Dear PyGui) to prevent
the display from sleeping during an active workout session. Call
enable_wake_lock() when a workout starts and disable_wake_lock() when it ends
(or on exit) to restore normal system sleep behaviour.
"""

import platform
import subprocess


class ScreenWakeKeeper:
    """Prevents the OS from sleeping during a workout session.

    Platform-aware: uses SetThreadExecutionState on Windows, caffeinate on
    macOS, and xset / systemd-inhibit on Linux.
    """

    def __init__(self):
        self.system = platform.system()
        self.wake_process = None
        self.wake_thread = None
        self.wake_stop_event = None

    def enable_wake_lock(self):
        try:
            if self.system == "Windows":
                import ctypes
                from threading import Thread, Event
                ES_CONTINUOUS = 0x80000000
                ES_DISPLAY_REQUIRED = 0x00000002
                ES_SYSTEM_REQUIRED = 0x00000001
                self.wake_stop_event = Event()

                def keep_awake():
                    while not self.wake_stop_event.is_set():
                        ctypes.windll.kernel32.SetThreadExecutionState(
                            ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED)
                        self.wake_stop_event.wait(5)

                self.wake_thread = Thread(target=keep_awake, daemon=True)
                self.wake_thread.start()
            elif self.system == "Darwin":
                self.wake_process = subprocess.Popen(
                    ['caffeinate', '-d', '-u'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif self.system == "Linux":
                try:
                    subprocess.run(['xset', 's', 'off'],
                                   capture_output=True, check=True)
                    subprocess.run(['xset', 's', 'noblank'],
                                   capture_output=True, check=True)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    self.wake_process = subprocess.Popen(
                        ['systemd-inhibit', '--what=sleep',
                         '--who=iSuper Bike Dashboard',
                         '--why=Workout in progress',
                         '--mode=block', 'sleep', 'infinity'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def disable_wake_lock(self):
        try:
            if self.system == "Windows" and self.wake_stop_event:
                self.wake_stop_event.set()
                if self.wake_thread:
                    self.wake_thread.join(timeout=2)
            elif self.wake_process:
                self.wake_process.terminate()
                self.wake_process.wait()
                self.wake_process = None
            if self.system == "Linux":
                try:
                    subprocess.run(['xset', 's', 'on'], capture_output=True)
                except FileNotFoundError:
                    pass
        except Exception:
            pass
