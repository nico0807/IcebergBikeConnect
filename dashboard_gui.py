#!/usr/bin/env python3
"""
iSuper Gym Bike Dashboard - Dear PyGui GUI
Window-based UI for displaying real-time sport data.
"""

import queue
import threading
import time
from collections import deque
from datetime import datetime

import dearpygui.dearpygui as dpg

from isuper_bike import ISuperBike
from sport_program_parser import SportProgramParser, SportProgram
from wake_keeper import ScreenWakeKeeper

# ---------------------------------------------------------------------------
# DPG item tag constants
# ---------------------------------------------------------------------------
TAG_MAIN_WINDOW = "main_window"
TAG_CONTENT_GROUP = "content_group"
TAG_PROGRESS_MODAL = "progress_modal"
TAG_PROGRESS_BAR = "progress_bar"
TAG_PROGRESS_TEXT = "progress_text"
TAG_STATUS_TEXT = "status_text"
TAG_DEVICE_INFO = "device_info"

TAG_TILE_SPEED = "tile_speed"
TAG_TILE_RPM = "tile_rpm"
TAG_TILE_HR = "tile_hr"
TAG_TILE_LEVEL = "tile_level"
TAG_TILE_DISTANCE = "tile_distance"
TAG_TILE_CALORIES = "tile_calories"
TAG_TILE_WATTS = "tile_watts"

TAG_GRAPH1_PLOT = "graph1_plot"
TAG_GRAPH1_SERIES = "graph1_series"
TAG_GRAPH1_XAXIS = "graph1_xaxis"
TAG_GRAPH1_YAXIS = "graph1_yaxis"
TAG_GRAPH1_COMBO = "graph1_combo"
TAG_GRAPH2_PLOT = "graph2_plot"
TAG_GRAPH2_SERIES = "graph2_series"
TAG_GRAPH2_XAXIS = "graph2_xaxis"
TAG_GRAPH2_YAXIS = "graph2_yaxis"
TAG_GRAPH2_COMBO = "graph2_combo"

TAG_PROGRAM_BAR_GROUP = "program_bar_group"
TAG_PROGRAM_BAR = "program_bar"
TAG_PROGRAM_TEXT = "program_text"

TAG_BTN_LEVEL_UP = "btn_level_up"
TAG_BTN_LEVEL_DOWN = "btn_level_down"
TAG_BTN_PAUSE = "btn_pause"
TAG_BTN_RESUME = "btn_resume"
TAG_BTN_RECONNECT = "btn_reconnect"
TAG_BTN_PROGRAM = "btn_program"
TAG_BTN_QUIT = "btn_quit"

TAG_PROG_MODAL = "prog_select_modal"
TAG_PROG_LISTBOX = "prog_listbox"
TAG_PROG_DURATION = "prog_duration"

# Theme tags
TAG_THEME_NORMAL = "theme_normal"
TAG_THEME_WARNING = "theme_warning"
TAG_THEME_ALERT = "theme_alert"
TAG_THEME_MAGENTA = "theme_magenta"
TAG_THEME_CYAN = "theme_cyan"

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
COL_BG = (12, 12, 12, 255)
COL_PANEL = (28, 28, 28, 255)
COL_CYAN = (0, 230, 255, 255)
COL_WHITE = (255, 255, 255, 255)
COL_GREEN = (60, 230, 60, 255)
COL_YELLOW = (255, 220, 0, 255)
COL_RED = (255, 60, 60, 255)
COL_MAGENTA = (210, 0, 240, 255)
COL_GREY = (160, 160, 160, 255)

METRIC_LABELS = {
    'speed':      'Speed (km/h)',
    'rpm':        'RPM',
    'heart_rate': 'Heart Rate (bpm)',
    'level':      'Level',
    'distance':   'Distance (km)',
    'calories':   'Calories (kcal)',
    'watts':      'Watts',
}
METRICS = list(METRIC_LABELS.keys())

# ---------------------------------------------------------------------------
# BikeWorker
# ---------------------------------------------------------------------------
class BikeWorker:
    """Owns ISuperBike. Runs connection + polling in a background thread."""

    POLL_INTERVAL = 0.1  # seconds

    def __init__(self, ip: str, msg_queue: queue.Queue):
        self.ip = ip
        self.queue = msg_queue
        self.bike = ISuperBike(ip, debug=False)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._busy = False  # True while connect/init/reconnect is running
        self.workout_start: datetime | None = None
        self.last_log_time: float = 0.0
        self.paused: bool = False
        self.active_program: SportProgram | None = None
        # --- Waiting-for-pedal state machine ---
        # When the user selects a program, we enter a waiting state instead of
        # starting immediately. The program only starts after PEDAL_REQUIRED_SECONDS
        # of continuous pedalling (RPM > 0). The GUI shows an orange progress bar
        # during this phase. Fields reset to defaults when the program launches or
        # is cancelled.
        self._pending_program: SportProgram | None = None
        self._pending_program_name: str = ''
        self.waiting_for_pedal: bool = False
        self._pedal_since: float = 0.0  # monotonic time when continuous pedalling started

    # ------------------------------------------------------------------
    # Public interface (called from GUI thread — thread-safe)
    # ------------------------------------------------------------------
    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.bike.stop_logging()
        self.bike.disconnect()

    def set_level(self, level):
        self.bike.set_level(level, self.bike.resistance_min,
                            self.bike.resistance_max)

    def pause(self):
        self.bike.pause_sport()
        self.paused = True

    def resume(self):
        self.bike.start_sport()
        self.paused = False

    def reconnect(self):
        if self._busy:
            return
        t = threading.Thread(target=self._do_reconnect, daemon=True)
        t.start()

    def queue_program(self, program: SportProgram, duration_minutes: int,
                      program_name: str):
        """Enter 'waiting for pedal' state; program starts after 3 s of pedalling."""
        program.duration_minutes = duration_minutes
        program.calculate_segment_duration()
        self._pending_program = program
        self._pending_program_name = program_name
        self.waiting_for_pedal = True
        self._pedal_since = 0.0

    def start_program(self, program: SportProgram, duration_minutes: int,
                      program_name: str):
        self.active_program = program
        self.active_program.duration_minutes = duration_minutes
        self.active_program.calculate_segment_duration()
        self.active_program.start()
        self.bike.stop_logging()
        self.bike.start_logging(program_name)

    def cancel_waiting(self):
        self._pending_program = None
        self._pending_program_name = ''
        self.waiting_for_pedal = False
        self._pedal_since = 0.0

    def clear_program(self):
        self.active_program = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _post(self, msg: dict):
        self.queue.put(msg)

    def _run(self):
        self._busy = True
        self._post(
            {'type': 'progress', 'message': f'Connecting to {self.ip}...'})

        self.bike.progress_callback = lambda m: self._post(
            {'type': 'progress', 'message': m})

        if not self.bike.connect():
            self._post({'type': 'error', 'message': 'Connection failed'})
            self._busy = False
            return

        if not self.bike.initialize():
            self._post({'type': 'error', 'message': 'Initialization failed'})
            self._busy = False
            return

        self._post({'type': 'progress', 'message': 'Ready!'})
        time.sleep(0.4)

        self.bike.start_sport()
        self.workout_start = datetime.now()
        self.bike.start_logging('manual')

        self._post({'type': 'connected'})
        self._busy = False

        self._poll_loop()

    def _do_reconnect(self):
        self._busy = True
        self._post({'type': 'progress', 'message': 'Reconnecting...'})
        self.bike.disconnect()
        time.sleep(1)

        if not self.bike.connect():
            self._post({'type': 'error', 'message': 'Reconnect failed'})
            self._busy = False
            return

        if not self.bike.initialize():
            self._post({'type': 'error', 'message': 'Re-init failed'})
            self._busy = False
            return

        self.bike.start_sport()
        self.workout_start = datetime.now()
        self._post({'type': 'connected'})
        self._busy = False
        self._poll_loop()

    PEDAL_REQUIRED_SECONDS = 3  # seconds of continuous pedalling to start program

    def _poll_loop(self):
        """Main background polling loop. Runs at POLL_INTERVAL (0.1 s) until stopped.

        Each iteration handles four concerns in order:
          1. CSV logging (1 s cadence)
          2. Waiting-for-pedal countdown — starts queued program after 3 s of RPM > 0
          3. Active program level updates (1 s cadence)
          4. Status snapshot posted to the GUI queue for tile/graph refresh
        """
        last_level_check = 0.0
        while not self._stop_event.is_set():
            if not self.bike.connected:
                self._post({'type': 'disconnected'})
                break

            if not self.paused:
                self.bike.receive_sport_data()

            now = time.time()

            # --- 1. CSV logging (1-second cadence) ---
            if self.workout_start and now - self.last_log_time >= 1.0:
                self.bike.log_data()
                self.last_log_time = now

            # --- 2. Waiting-for-pedal countdown ---
            # Tracks continuous RPM > 0; starts the program once PEDAL_REQUIRED_SECONDS
            # have elapsed. Resets the timer whenever pedalling stops.
            if self.waiting_for_pedal and self._pending_program is not None:
                rpm = self.bike.rpm
                if rpm and rpm > 0:
                    if self._pedal_since == 0.0:
                        self._pedal_since = now
                    elapsed_pedalling = now - self._pedal_since
                    pedal_progress = min(elapsed_pedalling / self.PEDAL_REQUIRED_SECONDS, 1.0)
                    self._post({'type': 'pedal_wait',
                                'progress': pedal_progress,
                                'remaining': max(0.0, self.PEDAL_REQUIRED_SECONDS - elapsed_pedalling)})
                    if elapsed_pedalling >= self.PEDAL_REQUIRED_SECONDS:
                        # Start the program now
                        self.waiting_for_pedal = False
                        prog = self._pending_program
                        name = self._pending_program_name
                        self._pending_program = None
                        self._pending_program_name = ''
                        self._pedal_since = 0.0
                        self.active_program = prog
                        self.active_program.start()
                        self.bike.stop_logging()
                        self.bike.start_logging(name)
                        self._post({'type': 'program_started'})
                else:
                    # Reset counter if pedalling stopped
                    self._pedal_since = 0.0
                    self._post({'type': 'pedal_wait', 'progress': 0.0,
                                'remaining': float(self.PEDAL_REQUIRED_SECONDS)})

            # --- 3. Active program: apply level changes (1-second cadence) ---
            if self.active_program and not self.paused:
                if now - last_level_check >= 1.0:
                    last_level_check = now
                    if not self.active_program.completed:
                        target = self.active_program.get_current_level()
                        if target and target != self.bike.level:
                            self.bike.set_level(
                                target,
                                self.bike.resistance_min,
                                self.bike.resistance_max)

            # --- 4. Post status snapshot to GUI queue ---
            status = self.bike.get_status()
            elapsed = (datetime.now() - self.workout_start).total_seconds() \
                if self.workout_start else 0.0
            self._post({'type': 'status', 'data': status, 'elapsed': elapsed})

            time.sleep(self.POLL_INTERVAL)


# ---------------------------------------------------------------------------
# GraphPanel
# ---------------------------------------------------------------------------
class GraphPanel:
    """One live-updating line plot with a metric selector combo."""

    HISTORY_SECONDS = 30
    MAX_POINTS = 300  # 30s × 10Hz

    def __init__(self, index: int, default_metric: str):
        self.index = index
        self.selected_metric = default_metric
        self._deque: deque = deque(maxlen=self.MAX_POINTS)

        prefix = f"graph{index}"
        self.tag_plot = f"{prefix}_plot"
        self.tag_series = f"{prefix}_series"
        self.tag_xaxis = f"{prefix}_xaxis"
        self.tag_yaxis = f"{prefix}_yaxis"
        self.tag_combo = f"{prefix}_combo"

    def build_ui(self, parent, width: int = -1, height: int = 300):
        w = width if width > 0 else -1
        with dpg.group(parent=parent):
            dpg.add_combo(
                tag=self.tag_combo,
                items=[METRIC_LABELS[m] for m in METRICS],
                default_value=METRIC_LABELS[self.selected_metric],
                width=w,
                callback=self._on_metric_change,
            )
            with dpg.plot(tag=self.tag_plot, height=height, width=w):
                dpg.add_plot_axis(dpg.mvXAxis, tag=self.tag_xaxis,
                                  label="Time (s)")
                with dpg.plot_axis(dpg.mvYAxis, tag=self.tag_yaxis,
                                   label=METRIC_LABELS[self.selected_metric]):
                    dpg.add_line_series([], [], tag=self.tag_series,
                                        label=METRIC_LABELS[self.selected_metric])
                    if dpg.does_item_exist("plot_line_theme"):
                        dpg.bind_item_theme(self.tag_series, "plot_line_theme")

    def _on_metric_change(self, sender, app_data):
        # Resolve label back to key
        for key, label in METRIC_LABELS.items():
            if label == app_data:
                self.selected_metric = key
                break
        self._deque.clear()
        dpg.set_value(self.tag_series, [[], []])
        dpg.set_item_label(self.tag_yaxis, METRIC_LABELS[self.selected_metric])
        dpg.set_item_label(
            self.tag_series, METRIC_LABELS[self.selected_metric])

    def push(self, status: dict, elapsed: float):
        value = float(status.get(self.selected_metric, 0))
        self._deque.append((elapsed, value))

        cutoff = elapsed - self.HISTORY_SECONDS
        visible = [(t, v) for t, v in self._deque if t >= cutoff]
        if not visible:
            return
        xs = [t for t, v in visible]
        ys = [v for t, v in visible]
        dpg.set_value(self.tag_series, [xs, ys])
        dpg.set_axis_limits(self.tag_xaxis, elapsed -
                            self.HISTORY_SECONDS, elapsed)
        dpg.fit_axis_data(self.tag_yaxis)

    def update_size(self, width: int, height: int):
        dpg.configure_item(self.tag_plot, width=width, height=height)
        dpg.configure_item(self.tag_combo, width=width)

# ---------------------------------------------------------------------------
# Time Helpers
# ---------------------------------------------------------------------------


def fmt_duration(seconds):
    """Format seconds as m:ss."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# Tile helpers
# ---------------------------------------------------------------------------
TILE_DEFS = [
    ('speed',      'Speed',      'km/h',  COL_GREEN,   [(None, None)]),
    ('rpm',        'RPM',        'rpm',   COL_GREEN,
     [(100, COL_YELLOW), (120, COL_RED)]),
    ('heart_rate', 'Heart Rate', 'bpm',   COL_GREEN,
     [(120, COL_YELLOW), (150, COL_RED)]),
    ('level',      'Level',      '',      COL_MAGENTA, [(None, None)]),
    ('distance',   'Distance',   'km',    COL_CYAN,    [(None, None)]),
    ('calories',   'Calories',   'kcal',  COL_MAGENTA, [(None, None)]),
    ('watts',      'Watts',      'W',     COL_GREEN,
     [(150, COL_YELLOW), (200, COL_RED)]),
]


def _tile_color(value: float, thresholds) -> tuple:
    """Return the appropriate colour for a value given threshold list."""
    color = thresholds[0][1] if thresholds[0][1] else COL_GREEN
    # thresholds is sorted ascending; walk through and upgrade color
    for thresh, col in thresholds:
        if thresh is not None and value >= thresh:
            color = col
    return color


# ---------------------------------------------------------------------------
# GUIDashboard
# ---------------------------------------------------------------------------
class GUIDashboard:
    """Main Dear PyGui application window for the iSuper Bike dashboard.

    Owns the DPG context, a BikeWorker background thread, and two GraphPanels.
    Handles responsive layout switching between wide (>=WIDE_BREAKPOINT px) and
    narrow layouts. All bike communication is asynchronous — BikeWorker posts
    messages to a queue that is drained each render frame in _on_frame.
    """

    WIDE_BREAKPOINT = 900
    DEBOUNCE_FRAMES = 3

    def __init__(self, ip: str, no_wake_lock: bool = False):
        self.ip = ip
        self.no_wake_lock = no_wake_lock

        self._queue: queue.Queue = queue.Queue()
        self.worker = BikeWorker(ip, self._queue)

        self.graph1 = GraphPanel(1, default_metric='heart_rate')
        self.graph2 = GraphPanel(2, 'rpm')

        self.wake_keeper = ScreenWakeKeeper()
        self.program_parser = SportProgramParser()
        self.program_parser.load_programs()

        self.layout_mode: str = 'wide'  # 'wide' or 'narrow'
        self._debounce_mode: str | None = None  # candidate mode being debounced
        self._debounce_count: int = 0           # consecutive frames in candidate mode

        self._last_status: dict | None = None
        self._connected: bool = False
        self._progress_value: float = 0.0  # animated fill for the connection progress bar
        # GUI-side cache of the worker's waiting-for-pedal progress, updated via
        # 'pedal_wait' queue messages (avoids reading worker state from GUI thread).
        self._pedal_wait_progress: float = 0.0
        self._pedal_wait_remaining: float = float(BikeWorker.PEDAL_REQUIRED_SECONDS)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def run(self):
        if not self.no_wake_lock:
            self.wake_keeper.enable_wake_lock()

        dpg.create_context()
        self._create_themes()
        self._create_fonts()
        self._setup_ui()

        dpg.create_viewport(title='iSuper Bike Dashboard', width=1280, height=900,
                            min_width=400, min_height=400)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window(TAG_MAIN_WINDOW, True)

        # Apply fonts to fixed header items
        if self.font_header:
            dpg.bind_item_font(TAG_STATUS_TEXT, self.font_header)
            # Also apply to title text (first text item in header group)
            # We tag it so we can reach it
            if dpg.does_item_exist("header_title"):
                dpg.bind_item_font("header_title", self.font_header)

        # Show progress modal and start worker
        dpg.configure_item(TAG_PROGRESS_MODAL, show=True)
        self.worker.start()

        # Main render loop
        while dpg.is_dearpygui_running():
            self._on_frame()
            dpg.render_dearpygui_frame()

        self._cleanup()
        dpg.destroy_context()

    # ------------------------------------------------------------------
    # Font creation
    # ------------------------------------------------------------------
    def _create_fonts(self):
        """Register font sizes. Falls back to Dear PyGui default if no TTF found."""
        import os
        # Try common system fonts; fall back gracefully if none found
        candidates = [
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        font_path = next((p for p in candidates if os.path.exists(p)), None)

        with dpg.font_registry():
            if font_path:
                self.font_large = dpg.add_font(font_path, 48)
                self.font_medium = dpg.add_font(font_path, 22)
                self.font_header = dpg.add_font(font_path, 28)
                self.font_program = dpg.add_font(font_path, 26)
            else:
                # No TTF found — DPG built-in only supports one size; use None (default)
                self.font_large = None
                self.font_medium = None
                self.font_header = None
                self.font_program = None

    # ------------------------------------------------------------------
    # Theme creation
    # ------------------------------------------------------------------
    def _create_themes(self):
        with dpg.theme(tag="global_theme"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg,     COL_BG)
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg,      COL_PANEL)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg,
                                    (45, 45, 45, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Button,
                                    (55, 55, 55, 255))
                dpg.add_theme_color(
                    dpg.mvThemeCol_ButtonHovered, (85, 85, 85, 255))
                dpg.add_theme_color(
                    dpg.mvThemeCol_ButtonActive, (110, 110, 110, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text,         COL_WHITE)
                dpg.add_theme_color(dpg.mvThemeCol_Border,
                                    (80, 80, 80, 255))
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding,  0)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,   2)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,     6, 4)
        dpg.bind_theme("global_theme")

        # Thick-line theme for plots
        with dpg.theme(tag="plot_line_theme"):
            with dpg.theme_component(dpg.mvLineSeries):
                dpg.add_theme_style(dpg.mvPlotStyleVar_LineWeight, 3.0,
                                    category=dpg.mvThemeCat_Plots)

        # Green progress bar theme (program complete)
        with dpg.theme(tag="bar_complete_theme"):
            with dpg.theme_component(dpg.mvProgressBar):
                dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram, COL_GREEN,
                                    category=dpg.mvThemeCat_Core)

        # Default progress bar theme
        with dpg.theme(tag="bar_normal_theme"):
            with dpg.theme_component(dpg.mvProgressBar):
                dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram, (0, 160, 200, 255),
                                    category=dpg.mvThemeCat_Core)

        # Orange progress bar theme (waiting for pedal)
        with dpg.theme(tag="bar_pedal_theme"):
            with dpg.theme_component(dpg.mvProgressBar):
                dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram, (220, 110, 0, 255),
                                    category=dpg.mvThemeCat_Core)

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------
    def _setup_ui(self):
        # Progress modal (always present, shown/hidden)
        with dpg.window(tag=TAG_PROGRESS_MODAL, label="Connecting",
                        modal=True, show=False,
                        width=400, height=130,
                        no_resize=True, no_move=True,
                        pos=[440, 335]):
            dpg.add_text("Please wait...",
                         tag=TAG_PROGRESS_TEXT, color=COL_WHITE)
            dpg.add_progress_bar(tag=TAG_PROGRESS_BAR,
                                 default_value=0.0, width=-1)

        # Main window
        with dpg.window(tag=TAG_MAIN_WINDOW, label="iSuper Bike Dashboard",
                        no_title_bar=True, no_resize=True, no_move=True,
                        no_scrollbar=True):
            # Fixed header
            with dpg.group(horizontal=True):
                dpg.add_text("  iSuper Bike Dashboard",
                             tag="header_title", color=COL_CYAN)
                dpg.add_spacer(width=20)
                dpg.add_text("○ DISCONNECTED",
                             tag=TAG_STATUS_TEXT, color=COL_RED)
            dpg.add_separator()

            # Content group — rebuilt on layout switch
            with dpg.group(tag=TAG_CONTENT_GROUP):
                self._build_content()

            dpg.add_separator()
            dpg.add_text("", tag=TAG_DEVICE_INFO, color=COL_GREY)

        # Program selection modal
        self._build_program_modal()

    def _build_content(self):
        """Build the layout-dependent content inside TAG_CONTENT_GROUP."""
        if self.layout_mode == 'wide':
            self._build_wide()
        else:
            self._build_narrow()

    def _build_wide(self):
        """Left: tile grid + program bar + controls. Right: two graphs."""
        with dpg.group(horizontal=True, parent=TAG_CONTENT_GROUP):
            # Left column
            with dpg.group():
                self._build_tile_grid(
                    columns=4, tile_width=160, tile_height=110)
                dpg.add_spacer(height=4)
                self._build_program_bar()
                dpg.add_spacer(height=4)
                self._build_controls()

            dpg.add_spacer(width=8)

            # Right column: two graphs stacked
            with dpg.group() as right_col:
                self.graph1.build_ui(parent=right_col, width=580, height=280)
                dpg.add_spacer(height=6)
                self.graph2.build_ui(parent=right_col, width=580, height=280)

    def _build_narrow(self):
        """Single column: tiles, graph1, graph2, program bar, controls."""
        with dpg.group(parent=TAG_CONTENT_GROUP) as col:
            self._build_tile_grid(columns=2, tile_width=180, tile_height=160)
            dpg.add_spacer(height=4)
            self.graph1.build_ui(parent=col, width=-1, height=180)
            dpg.add_spacer(height=4)
            self.graph2.build_ui(parent=col, width=-1, height=180)
            dpg.add_spacer(height=4)
            self._build_program_bar()
            dpg.add_spacer(height=4)
            self._build_controls(wrap=True)

    def _build_tile_grid(self, columns: int, tile_width: int, tile_height: int):
        """Render metric tiles in a grid with the given number of columns."""
        row_group = None
        for i, (key, label, unit, default_color, thresholds) in enumerate(TILE_DEFS):
            if i % columns == 0:
                row_group = dpg.add_group(horizontal=True,
                                          parent=TAG_CONTENT_GROUP)
            with dpg.child_window(parent=row_group, border=True,
                                  width=tile_width, height=tile_height,
                                  tag=f"tile_{key}_win"):
                if self.font_medium:
                    dpg.add_text(f"{label}", color=COL_GREY)
                    dpg.bind_item_font(dpg.last_item(), self.font_medium)
                else:
                    dpg.add_text(label, color=COL_GREY)
                val_tag = f"tile_{key}_val"
                dpg.add_text("---", tag=val_tag, color=default_color)
                if self.font_large:
                    dpg.bind_item_font(val_tag, self.font_large)
                if unit:
                    dpg.add_text(unit, color=COL_GREY)
                    if self.font_medium:
                        dpg.bind_item_font(dpg.last_item(), self.font_medium)

    def _build_program_bar(self):
        with dpg.group(tag=TAG_PROGRAM_BAR_GROUP, parent=TAG_CONTENT_GROUP, show=False):
            dpg.add_progress_bar(tag=TAG_PROGRAM_BAR, default_value=0.0, width=-1,
                                 height=28, overlay="No program")
            dpg.add_text("", tag=TAG_PROGRAM_TEXT, color=COL_CYAN)
            if self.font_program:
                dpg.bind_item_font(TAG_PROGRAM_TEXT, self.font_program)

    def _make_button(self, tag: str, label: str, width: int,
                     height: int, callback, parent=None) -> None:
        """Add a single control button and bind the medium font if available."""
        kwargs = dict(tag=tag, label=label, width=width, height=height,
                      callback=callback)
        if parent is not None:
            kwargs['parent'] = parent
        dpg.add_button(**kwargs)
        if self.font_medium:
            dpg.bind_item_font(tag, self.font_medium)

    def _build_controls(self, wrap: bool = False):
        """Build the row(s) of control buttons.

        wrap=False (wide layout): all 6 controls in one horizontal row, Quit below.
        wrap=True  (narrow layout): controls split into two rows of 3, Quit below.
        """
        btn_w = 120
        bh = 40
        if not wrap:
            with dpg.group(horizontal=True, parent=TAG_CONTENT_GROUP):
                self._make_button(TAG_BTN_LEVEL_UP,   "+ Level",   btn_w, bh, self._on_level_up)
                self._make_button(TAG_BTN_LEVEL_DOWN, "- Level",   btn_w, bh, self._on_level_down)
                self._make_button(TAG_BTN_PAUSE,      "Pause",     btn_w, bh, self._on_pause)
                self._make_button(TAG_BTN_RESUME,     "Resume",    btn_w, bh, self._on_resume)
                self._make_button(TAG_BTN_RECONNECT,  "Reconnect", btn_w, bh, self._on_reconnect)
                self._make_button(TAG_BTN_PROGRAM,    "Program",   btn_w, bh, self._on_open_program)
            self._make_button(TAG_BTN_QUIT, "Quit", 80, bh, self._on_quit,
                              parent=TAG_CONTENT_GROUP)
        else:
            # Two rows of 3 for narrow layout
            with dpg.group(parent=TAG_CONTENT_GROUP):
                with dpg.group(horizontal=True):
                    self._make_button(TAG_BTN_LEVEL_UP,   "+ Level",   btn_w, bh, self._on_level_up)
                    self._make_button(TAG_BTN_LEVEL_DOWN, "- Level",   btn_w, bh, self._on_level_down)
                    self._make_button(TAG_BTN_PAUSE,      "Pause",     btn_w, bh, self._on_pause)
                with dpg.group(horizontal=True):
                    self._make_button(TAG_BTN_RESUME,     "Resume",    btn_w, bh, self._on_resume)
                    self._make_button(TAG_BTN_RECONNECT,  "Reconnect", btn_w, bh, self._on_reconnect)
                    self._make_button(TAG_BTN_PROGRAM,    "Program",   btn_w, bh, self._on_open_program)
                self._make_button(TAG_BTN_QUIT, "Quit", btn_w, bh, self._on_quit)

    def _build_program_modal(self):
        programs = self.program_parser.list_programs()
        names = [p.name for p in programs] if programs else [
            "(no programs found)"]
        with dpg.window(tag=TAG_PROG_MODAL, label="Select Program",
                        modal=True, show=False,
                        width=360, height=240,
                        no_resize=True):
            dpg.add_text("Choose a program:", color=COL_CYAN)
            dpg.add_listbox(tag=TAG_PROG_LISTBOX, items=names,
                            num_items=min(6, len(names)), width=-1)
            dpg.add_spacer(height=4)
            dpg.add_text("Duration (minutes):", color=COL_GREY)
            dpg.add_input_int(tag=TAG_PROG_DURATION, default_value=30,
                              min_value=1, max_value=180, width=120)
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Start", width=80,
                               callback=self._on_program_start)
                dpg.add_button(label="Cancel", width=80,
                               callback=lambda: dpg.configure_item(
                                   TAG_PROG_MODAL, show=False))

    # ------------------------------------------------------------------
    # Responsive layout switching
    # ------------------------------------------------------------------
    def _rebuild_layout(self):
        """Delete and recreate content region for the new layout mode."""
        # Delete all children of content group
        children = dpg.get_item_children(TAG_CONTENT_GROUP, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        # Also delete graph DPG items that were inside (they're gone with children)
        # Re-assign fresh GraphPanel objects to reset internal state cleanly
        self.graph1 = GraphPanel(1, self.graph1.selected_metric)
        self.graph2 = GraphPanel(2, self.graph2.selected_metric)

        self._build_content()

        # Re-apply program bar visibility
        if self.worker.active_program:
            dpg.configure_item(TAG_PROGRAM_BAR_GROUP, show=True)
        else:
            dpg.configure_item(TAG_PROGRAM_BAR_GROUP, show=False)

        # Re-apply connection state to buttons
        self._set_buttons_enabled(self._connected)

    # ------------------------------------------------------------------
    # Frame callback
    # ------------------------------------------------------------------
    def _on_frame(self):
        # --- Responsive check ---
        vp_w = dpg.get_viewport_width()
        new_mode = 'wide' if vp_w >= self.WIDE_BREAKPOINT else 'narrow'

        if new_mode != self.layout_mode:
            if new_mode == self._debounce_mode:
                self._debounce_count += 1
            else:
                self._debounce_mode = new_mode
                self._debounce_count = 1

            if self._debounce_count >= self.DEBOUNCE_FRAMES:
                self.layout_mode = new_mode
                self._debounce_mode = None
                self._debounce_count = 0
                self._rebuild_layout()
        else:
            self._debounce_mode = None
            self._debounce_count = 0

        # --- Drain queue ---
        for _ in range(20):
            try:
                msg = self._queue.get_nowait()
            except queue.Empty:
                break
            self._handle_msg(msg)

    def _handle_msg(self, msg: dict):
        """Dispatch a single message from the BikeWorker queue.

        Message types:
          'progress'        — connection progress text + animated bar fill
          'connected'       — bike is ready; show tiles, enable buttons
          'disconnected'    — bike lost; disable buttons
          'error'           — show error text in progress modal
          'pedal_wait'      — waiting-for-pedal countdown update (progress, remaining)
          'program_started' — pedal wait complete; program is now active
          'status'          — periodic bike data snapshot for tiles, graphs, program bar
        """
        mtype = msg['type']

        if mtype == 'progress':
            text = msg['message']
            dpg.set_value(TAG_PROGRESS_TEXT, text)
            self._progress_value = min(1.0, self._progress_value + 0.12)
            dpg.set_value(TAG_PROGRESS_BAR, self._progress_value)

        elif mtype == 'connected':
            self._connected = True
            self._progress_value = 1.0
            dpg.set_value(TAG_PROGRESS_BAR, 1.0)
            dpg.configure_item(TAG_PROGRESS_MODAL, show=False)
            dpg.set_value(TAG_STATUS_TEXT, "● CONNECTED")
            dpg.configure_item(TAG_STATUS_TEXT, color=COL_GREEN)
            self._set_buttons_enabled(True)
            status = self.worker.bike.get_status()
            dpg.set_value(TAG_DEVICE_INFO,
                          f"  IP: {self.ip}  |  MAC: {status['mac_address'] or 'N/A'}"
                          f"  |  Wheel: {status['wheel_diameter']:.2f}\"  "
                          f"|  Resistance: {status['resistance_min']}-{status['resistance_max']}")

        elif mtype == 'disconnected':
            self._connected = False
            dpg.set_value(TAG_STATUS_TEXT, "○ DISCONNECTED")
            dpg.configure_item(TAG_STATUS_TEXT, color=COL_RED)
            self._set_buttons_enabled(False)

        elif mtype == 'error':
            dpg.set_value(TAG_PROGRESS_TEXT, f"Error: {msg['message']}")
            dpg.configure_item(TAG_PROGRESS_MODAL, show=True)

        elif mtype == 'pedal_wait':
            self._pedal_wait_progress = msg['progress']
            self._pedal_wait_remaining = msg['remaining']
            self._update_program_bar()

        elif mtype == 'program_started':
            self._pedal_wait_progress = 0.0
            self._pedal_wait_remaining = 0.0
            self._update_program_bar()

        elif mtype == 'status':
            self._last_status = msg['data']
            elapsed = msg['elapsed']
            self._update_tiles(self._last_status)
            self.graph1.push(self._last_status, elapsed)
            self.graph2.push(self._last_status, elapsed)
            self._update_program_bar()
            # Update message counts
            s = self._last_status
            dpg.set_value(TAG_DEVICE_INFO,
                          f"  IP: {self.ip}  |  MAC: {s['mac_address'] or 'N/A'}"
                          f"  |  Wheel: {s['wheel_diameter']:.2f}\"  "
                          f"|  Resistance: {s['resistance_min']}-{s['resistance_max']}"
                          f"  |  Sent: {s['messages_sent']}  Recv: {s['messages_received']}"
                          f"  |  {s['last_update'].strftime('%H:%M:%S') if s['last_update'] else '--:--:--'}")

    def _update_tiles(self, status: dict):
        for key, label, unit, default_color, thresholds in TILE_DEFS:
            val = float(status.get(key, 0))
            tag = f"tile_{key}_val"
            if not dpg.does_item_exist(tag):
                continue
            if key in ('rpm', 'heart_rate', 'level', 'watts'):
                text = f"{int(val)}"
            elif key == 'distance':
                text = f"{val:.3f}"
            elif key == 'calories':
                text = f"{val:.1f}"
            else:
                text = f"{val:.1f}"
            color = _tile_color(val, thresholds)
            dpg.set_value(tag, text)
            dpg.configure_item(tag, color=color)

    def _update_program_bar(self):
        if not dpg.does_item_exist(TAG_PROGRAM_BAR_GROUP):
            return

        # Waiting-for-pedal state: show orange bar with countdown
        if self.worker.waiting_for_pedal and self.worker._pending_program is not None:
            dpg.configure_item(TAG_PROGRAM_BAR_GROUP, show=True)
            remaining = self._pedal_wait_remaining
            dpg.set_value(TAG_PROGRAM_BAR, self._pedal_wait_progress)
            dpg.configure_item(TAG_PROGRAM_BAR,
                               overlay=f"Waiting for pedal...  {remaining:.1f}s")
            dpg.set_value(TAG_PROGRAM_TEXT, "Start pedalling to begin the program")
            dpg.configure_item(TAG_PROGRAM_TEXT, color=(220, 110, 0, 255))
            if dpg.does_item_exist("bar_pedal_theme"):
                dpg.bind_item_theme(TAG_PROGRAM_BAR, "bar_pedal_theme")
            return

        prog = self.worker.active_program
        if not prog:
            return
        dpg.configure_item(TAG_PROGRAM_BAR_GROUP, show=True)
        progress, remaining, seg = prog.get_progress()
        current_level, seg_remaining, _ = prog.get_current_segment_info()
        dpg.set_value(TAG_PROGRAM_BAR, progress / 100.0)
        dpg.configure_item(TAG_PROGRAM_BAR,
                           overlay=f"{prog.name}  {progress:.0f}%  Seg {seg}/{prog.total_segments}  Next: {fmt_duration(seg_remaining)}")
        if prog.completed:
            dpg.set_value(TAG_PROGRAM_TEXT, "PROGRAM COMPLETE!")
            dpg.configure_item(TAG_PROGRAM_TEXT, color=COL_GREEN)
            if dpg.does_item_exist("bar_complete_theme"):
                dpg.bind_item_theme(TAG_PROGRAM_BAR, "bar_complete_theme")
        else:
            status_text = (f"Level: {current_level if current_level else 'N/A'}"
                           f"  |  {fmt_duration(remaining)} remaining")
            dpg.set_value(TAG_PROGRAM_TEXT, status_text)
            dpg.configure_item(TAG_PROGRAM_TEXT, color=COL_CYAN)
            if dpg.does_item_exist("bar_normal_theme"):
                dpg.bind_item_theme(TAG_PROGRAM_BAR, "bar_normal_theme")

    def _set_buttons_enabled(self, enabled: bool):
        for tag in (TAG_BTN_LEVEL_UP, TAG_BTN_LEVEL_DOWN,
                    TAG_BTN_PAUSE, TAG_BTN_RESUME, TAG_BTN_PROGRAM):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=enabled)
        if dpg.does_item_exist(TAG_BTN_RECONNECT):
            # always available
            dpg.configure_item(TAG_BTN_RECONNECT, enabled=True)

    # ------------------------------------------------------------------
    # Control callbacks
    # ------------------------------------------------------------------
    def _on_level_up(self):
        if self.worker.bike:
            self.worker.set_level(self.worker.bike.level + 1)

    def _on_level_down(self):
        if self.worker.bike:
            self.worker.set_level(self.worker.bike.level - 1)

    def _on_pause(self):
        self.worker.pause()

    def _on_resume(self):
        self.worker.resume()

    def _on_reconnect(self):
        self.worker.reconnect()
        dpg.configure_item(TAG_PROGRESS_MODAL, show=True)
        self._progress_value = 0.0
        dpg.set_value(TAG_PROGRESS_BAR, 0.0)
        dpg.set_value(TAG_PROGRESS_TEXT, "Reconnecting...")

    def _on_open_program(self):
        programs = self.program_parser.list_programs()
        if programs:
            dpg.configure_item(TAG_PROG_MODAL, show=True)

    def _on_program_start(self):
        programs = self.program_parser.list_programs()
        if not programs:
            dpg.configure_item(TAG_PROG_MODAL, show=False)
            return
        selected_name = dpg.get_value(TAG_PROG_LISTBOX)
        program = next((p for p in programs if p.name ==
                       selected_name), programs[0])
        duration = dpg.get_value(TAG_PROG_DURATION)
        self.worker.queue_program(
            program, duration, program.name.replace(' ', '_').lower())
        self._pedal_wait_progress = 0.0
        self._pedal_wait_remaining = float(BikeWorker.PEDAL_REQUIRED_SECONDS)
        if dpg.does_item_exist(TAG_PROGRAM_BAR_GROUP):
            dpg.configure_item(TAG_PROGRAM_BAR_GROUP, show=True)
        self._update_program_bar()
        dpg.configure_item(TAG_PROG_MODAL, show=False)

    def _on_quit(self):
        dpg.stop_dearpygui()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def _cleanup(self):
        self.worker.stop()
        if not self.no_wake_lock:
            self.wake_keeper.disable_wake_lock()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    import argparse
    import getpass
    import socket

    parser = argparse.ArgumentParser(description='iSuper Bike Dashboard (GUI)')
    parser.add_argument('--ip', default='169.254.1.1',
                        help='Bike IP address (default: 169.254.1.1)')
    parser.add_argument('--list-ips', action='store_true',
                        help='Scan for available bikes on local network')
    parser.add_argument('--configure-ap', metavar='SSID',
                        help='Configure bike AP mode with WiFi SSID')
    parser.add_argument('--no-wake-lock', action='store_true',
                        help='Disable wake lock')
    args = parser.parse_args()

    if args.configure_ap:
        print(f"\n=== AP Configuration Mode ===")
        print(f"Target SSID: {args.configure_ap}")
        password = getpass.getpass("Enter WiFi password (hidden): ")
        bike = ISuperBike(args.ip, debug=False)
        print(f"Connecting to bike at {args.ip}...")
        if bike.connect():
            time.sleep(0.5)
            if bike.initialize():
                time.sleep(0.5)
                bike.configure_ap(args.configure_ap, password)
                bike.disconnect()
            else:
                print("Failed to initialize bike connection")
        else:
            print("Failed to connect to bike")
        return

    if args.list_ips:
        print("Scanning for bikes...")
        for ip in ["192.168.4.1", "192.168.1.1", "192.168.0.1",
                   "196.254.1.1", "169.254.1.1"]:
            print(f"Trying {ip}...", end=" ", flush=True)
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.0)
                result = s.connect_ex((ip, 1971))
                s.close()
                print("FOUND!" if result == 0 else "not found")
            except Exception as e:
                print(f"error: {e}")
        return

    GUIDashboard(args.ip, args.no_wake_lock).run()


if __name__ == "__main__":
    main()
