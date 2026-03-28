#!/usr/bin/env python3
"""
Sport Program Editor
Graphical editor for iSuper bike sport program files using DearPyGui.
"""

import dearpygui.dearpygui as dpg
import os
import re

# --- Constants ---
SPORT_PROGRAMS_DIR = "sport_programs"
MIN_LEVEL = 1
MAX_LEVEL = 20
GRAPH_W = 700
GRAPH_H = 300
GRAPH_PAD_L = 50
GRAPH_PAD_R = 20
GRAPH_PAD_T = 20
GRAPH_PAD_B = 55

# --- State ---
segments = []       # list of int levels, index = segment number - 1
current_file = None
unsaved = False
session_minutes = 30  # total session duration in minutes


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def parse_file(filepath):
    """Parse a sport program file. Returns list of levels (1-based segment order)."""
    segs = []
    try:
        with open(filepath, "r") as f:
            content = f.read()
        seg_matches = re.findall(r"SEG:(\d+):(\d+)", content)
        pairs = [(int(n), int(lvl)) for n, lvl in seg_matches]
        pairs.sort(key=lambda x: x[0])
        segs = [lvl for _, lvl in pairs]
    except Exception as e:
        show_status(f"Error reading file: {e}", error=True)
    return segs


def serialize_segments(segs):
    """Build file content from a list of levels."""
    lines = []
    lines.append(f"SEGMENTS:{len(segs)}")
    for i, lvl in enumerate(segs):
        lines.append(f"SEG:{i+1}:{lvl}")
    lines.append("END")
    lines.append("")
    return "\n".join(lines)


def save_file(filepath, segs):
    try:
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
        with open(filepath, "w") as f:
            f.write(serialize_segments(segs))
        return True
    except Exception as e:
        show_status(f"Error saving: {e}", error=True)
        return False


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

def segment_duration_seconds():
    """Return the duration of each segment in seconds, or 0 if no segments."""
    if not segments:
        return 0
    return (session_minutes * 60) / len(segments)


def fmt_duration(seconds):
    """Format seconds as m:ss."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def update_seg_duration_hint():
    if segments:
        secs = segment_duration_seconds()
        dpg.set_value("seg_duration_hint", f"→  {fmt_duration(secs)} per segment")
    else:
        dpg.set_value("seg_duration_hint", "")


def show_status(msg, error=False):
    color = (255, 80, 80, 255) if error else (100, 220, 100, 255)
    dpg.set_value("status_text", msg)
    dpg.configure_item("status_text", color=color)


def mark_unsaved():
    global unsaved
    unsaved = True
    update_title()


def update_title():
    name = os.path.basename(current_file) if current_file else "Untitled"
    marker = " *" if unsaved else ""
    dpg.set_value("title_text", f"Program: {name}{marker}")


# ---------------------------------------------------------------------------
# Graph drawing
# ---------------------------------------------------------------------------

def redraw_graph():
    """Redraw the step-line graph inside the drawlist."""
    update_seg_duration_hint()
    dpg.delete_item("graph_draw", children_only=True)

    n = len(segments)
    w = GRAPH_W
    h = GRAPH_H
    pl = GRAPH_PAD_L
    pr = GRAPH_PAD_R
    pt = GRAPH_PAD_T
    pb = GRAPH_PAD_B

    inner_w = w - pl - pr
    inner_h = h - pt - pb

    # Background
    dpg.draw_rectangle(
        (0, 0), (w, h),
        color=(30, 30, 30, 255),
        fill=(30, 30, 30, 255),
        parent="graph_draw",
    )

    # Grid lines (horizontal, per level)
    level_range = MAX_LEVEL - MIN_LEVEL
    grid_step = 2
    for lvl in range(MIN_LEVEL, MAX_LEVEL + 1, grid_step):
        y = pt + inner_h - int((lvl - MIN_LEVEL) / level_range * inner_h)
        dpg.draw_line(
            (pl, y), (w - pr, y),
            color=(60, 60, 60, 255),
            thickness=1,
            parent="graph_draw",
        )
        dpg.draw_text(
            (2, y - 7),
            str(lvl),
            color=(150, 150, 150, 255),
            size=13,
            parent="graph_draw",
        )

    # Axes
    dpg.draw_line(
        (pl, pt), (pl, h - pb),
        color=(180, 180, 180, 255),
        thickness=2,
        parent="graph_draw",
    )
    dpg.draw_line(
        (pl, h - pb), (w - pr, h - pb),
        color=(180, 180, 180, 255),
        thickness=2,
        parent="graph_draw",
    )

    if n == 0:
        dpg.draw_text(
            (w // 2 - 80, h // 2 - 10),
            "No segments — add one below",
            color=(180, 180, 180, 255),
            size=16,
            parent="graph_draw",
        )
        return

    seg_w = inner_w / n

    def seg_x(i):
        return pl + i * seg_w

    def level_y(lvl):
        return pt + inner_h - int((lvl - MIN_LEVEL) / level_range * inner_h)

    # Filled area under step graph
    fill_pts = [(seg_x(0), h - pb)]
    for i, lvl in enumerate(segments):
        x0 = seg_x(i)
        x1 = seg_x(i + 1)
        y = level_y(lvl)
        fill_pts.append((x0, y))
        fill_pts.append((x1, y))
    fill_pts.append((seg_x(n), h - pb))
    dpg.draw_polygon(
        fill_pts,
        color=(0, 0, 0, 0),
        fill=(50, 120, 200, 60),
        parent="graph_draw",
    )

    # Step lines + segment bars
    for i, lvl in enumerate(segments):
        x0 = seg_x(i)
        x1 = seg_x(i + 1)
        y = level_y(lvl)

        # Segment rectangle (subtle)
        dpg.draw_rectangle(
            (x0 + 1, y),
            (x1 - 1, h - pb),
            color=(0, 0, 0, 0),
            fill=(50, 120, 200, 40),
            parent="graph_draw",
        )

        # Horizontal level line
        dpg.draw_line(
            (x0, y), (x1, y),
            color=(80, 170, 255, 255),
            thickness=3,
            parent="graph_draw",
        )

        # Vertical connector to next segment
        if i < n - 1:
            y_next = level_y(segments[i + 1])
            dpg.draw_line(
                (x1, y), (x1, y_next),
                color=(80, 170, 255, 200),
                thickness=2,
                parent="graph_draw",
            )

        seg_secs = segment_duration_seconds()
        start_secs = i * seg_secs

        # Segment number label
        cx = (x0 + x1) / 2
        seg_label = str(i + 1)
        dpg.draw_text(
            (cx - 4, h - pb + 4),
            seg_label,
            color=(180, 180, 180, 255),
            size=12,
            parent="graph_draw",
        )

        # Start-time label below segment number (only if there's enough room)
        if seg_secs > 0 and seg_w > 30:
            time_label = fmt_duration(start_secs)
            dpg.draw_text(
                (cx - 10, h - pb + 17),
                time_label,
                color=(100, 160, 220, 200),
                size=11,
                parent="graph_draw",
            )

        # Level label on bar
        dpg.draw_text(
            (cx - 5, y - 18),
            str(lvl),
            color=(220, 220, 80, 255),
            size=13,
            parent="graph_draw",
        )

    # Axis label — only show "Segments" if no time labels (not enough height/room)
    dpg.draw_text(
        (2, h - 12),
        "Level",
        color=(150, 150, 150, 255),
        size=12,
        parent="graph_draw",
    )


# ---------------------------------------------------------------------------
# Segment list (table rows)
# ---------------------------------------------------------------------------

def rebuild_segment_table():
    dpg.delete_item("seg_table", children_only=True)

    seg_secs = segment_duration_seconds()

    # Header
    dpg.add_table_column(label="#", parent="seg_table", width_fixed=True, init_width_or_weight=30)
    dpg.add_table_column(label="Start time", parent="seg_table", width_fixed=True, init_width_or_weight=75)
    dpg.add_table_column(label="Duration", parent="seg_table", width_fixed=True, init_width_or_weight=70)
    dpg.add_table_column(label="Level", parent="seg_table", width_fixed=True, init_width_or_weight=80)
    dpg.add_table_column(label="Actions", parent="seg_table")

    for i, lvl in enumerate(segments):
        start_secs = i * seg_secs
        with dpg.table_row(parent="seg_table"):
            dpg.add_text(str(i + 1))
            dpg.add_text(fmt_duration(start_secs), color=(160, 200, 255, 255))
            dpg.add_text(fmt_duration(seg_secs), color=(160, 160, 160, 255))

            # Inline level spinbox
            dpg.add_input_int(
                default_value=lvl,
                min_value=MIN_LEVEL,
                max_value=MAX_LEVEL,
                min_clamped=True,
                max_clamped=True,
                width=70,
                tag=f"seg_level_{i}",
                callback=on_level_change,
                user_data=i,
            )

            with dpg.group(horizontal=True):
                dpg.add_button(label="^", width=28, callback=on_move_up, user_data=i,
                               enabled=(i > 0))
                dpg.add_button(label="v", width=28, callback=on_move_down, user_data=i,
                               enabled=(i < len(segments) - 1))
                dpg.add_button(label="Del", width=40, callback=on_delete_segment, user_data=i,
                               small=True)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def on_session_time_change(sender, value, user_data):
    global session_minutes
    session_minutes = max(1, value)
    rebuild_segment_table()
    redraw_graph()


def on_level_change(sender, value, user_data):
    idx = user_data
    segments[idx] = value
    mark_unsaved()
    redraw_graph()


def on_add_segment(sender, app_data):
    level = dpg.get_value("new_seg_level")
    segments.append(level)
    mark_unsaved()
    rebuild_segment_table()
    redraw_graph()
    show_status(f"Added segment {len(segments)} at level {level}")


def on_delete_segment(sender, app_data, user_data):
    idx = user_data
    removed_level = segments.pop(idx)
    mark_unsaved()
    rebuild_segment_table()
    redraw_graph()
    show_status(f"Removed segment {idx + 1} (was level {removed_level})")


def on_move_up(sender, app_data, user_data):
    idx = user_data
    if idx > 0:
        segments[idx], segments[idx - 1] = segments[idx - 1], segments[idx]
        mark_unsaved()
        rebuild_segment_table()
        redraw_graph()


def on_move_down(sender, app_data, user_data):
    idx = user_data
    if idx < len(segments) - 1:
        segments[idx], segments[idx + 1] = segments[idx + 1], segments[idx]
        mark_unsaved()
        rebuild_segment_table()
        redraw_graph()


def on_new_file(sender=None, app_data=None):
    global segments, current_file, unsaved
    segments = []
    current_file = None
    unsaved = False
    update_title()
    rebuild_segment_table()
    redraw_graph()
    show_status("New program — add segments below")


def on_open_dialog(sender=None, app_data=None):
    dpg.show_item("open_dialog")


def on_open_file(sender, app_data):
    global segments, current_file, unsaved
    path = app_data.get("file_path_name", "")
    if not path:
        return
    segs = parse_file(path)
    if segs is not None:
        segments = segs
        current_file = path
        unsaved = False
        update_title()
        rebuild_segment_table()
        redraw_graph()
        show_status(f"Opened: {os.path.basename(path)} ({len(segments)} segments)")


def on_save(sender=None, app_data=None):
    global unsaved
    if not current_file:
        dpg.show_item("save_dialog")
        return
    if save_file(current_file, segments):
        unsaved = False
        update_title()
        show_status(f"Saved: {os.path.basename(current_file)}")


def on_save_as(sender=None, app_data=None):
    dpg.show_item("save_dialog")


def on_save_file(sender, app_data):
    global current_file, unsaved
    path = app_data.get("file_path_name", "")
    if not path:
        return
    if not path.endswith(".txt"):
        path += ".txt"
    if save_file(path, segments):
        current_file = path
        unsaved = False
        update_title()
        show_status(f"Saved: {os.path.basename(path)}")


# ---------------------------------------------------------------------------
# Build UI
# ---------------------------------------------------------------------------

def build_ui():
    with dpg.window(tag="main_win", label="Sport Program Editor", no_title_bar=True,
                    no_move=True, no_resize=True, no_close=True,
                    pos=(0, 0), width=800, height=700):

        # --- Top bar ---
        with dpg.group(horizontal=True):
            dpg.add_text("Sport Program Editor", color=(200, 200, 255, 255))
            dpg.add_spacer(width=20)
            dpg.add_button(label="New", width=55, callback=on_new_file)
            dpg.add_button(label="Open", width=55, callback=on_open_dialog)
            dpg.add_button(label="Save", width=55, callback=on_save)
            dpg.add_button(label="Save As", width=70, callback=on_save_as)

        dpg.add_text("", tag="title_text", color=(180, 180, 100, 255))
        dpg.add_text("", tag="status_text", color=(100, 220, 100, 255))

        # --- Session time ---
        with dpg.group(horizontal=True):
            dpg.add_text("Session duration (min):", color=(200, 200, 200, 255))
            dpg.add_input_int(
                tag="session_minutes",
                default_value=session_minutes,
                min_value=1,
                max_value=300,
                min_clamped=True,
                max_clamped=True,
                width=80,
                callback=on_session_time_change,
            )
            dpg.add_text("", tag="seg_duration_hint", color=(160, 160, 160, 255))

        dpg.add_separator()

        # --- Graph ---
        with dpg.drawlist(width=GRAPH_W, height=GRAPH_H, tag="graph_draw"):
            pass

        dpg.add_separator()

        # --- Add segment bar ---
        dpg.add_text("Add Segment:", color=(200, 200, 200, 255))
        with dpg.group(horizontal=True):
            dpg.add_text("Level:")
            dpg.add_input_int(
                tag="new_seg_level",
                default_value=5,
                min_value=MIN_LEVEL,
                max_value=MAX_LEVEL,
                min_clamped=True,
                max_clamped=True,
                width=80,
            )
            dpg.add_button(label="Add Segment", callback=on_add_segment)

        dpg.add_separator()

        # --- Segment table ---
        dpg.add_text("Segments:", color=(200, 200, 200, 255))
        with dpg.child_window(height=200, border=True):
            with dpg.table(
                tag="seg_table",
                borders_innerH=True,
                borders_outerH=True,
                borders_outerV=True,
                row_background=True,
                resizable=False,
                policy=dpg.mvTable_SizingFixedFit,
            ):
                pass  # columns added in rebuild_segment_table

    # --- File dialogs ---
    with dpg.file_dialog(
        tag="open_dialog",
        label="Open Program File",
        callback=on_open_file,
        cancel_callback=lambda s, a: None,
        default_path=os.path.abspath(SPORT_PROGRAMS_DIR),
        width=600,
        height=400,
        modal=True,
        show=False,
    ):
        dpg.add_file_extension(".txt", color=(100, 220, 100, 255))
        dpg.add_file_extension(".*")

    with dpg.file_dialog(
        tag="save_dialog",
        label="Save Program File",
        callback=on_save_file,
        cancel_callback=lambda s, a: None,
        default_path=os.path.abspath(SPORT_PROGRAMS_DIR),
        width=600,
        height=400,
        modal=True,
        show=False,
        file_count=0,
    ):
        dpg.add_file_extension(".txt", color=(100, 220, 100, 255))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    dpg.create_context()
    dpg.create_viewport(title="iSuper Sport Program Editor", width=900, height=780, resizable=True)

    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (22, 22, 28, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (40, 40, 50, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (50, 100, 160, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (70, 130, 200, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (40, 80, 140, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Header, (50, 100, 160, 255))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (70, 130, 200, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBg, (28, 28, 36, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt, (36, 36, 46, 255))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 12, 10)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 6)

    dpg.bind_theme(global_theme)

    build_ui()
    on_new_file()

    dpg.setup_dearpygui()
    dpg.show_viewport()

    # Fit inner window to viewport now and on every resize
    def fit_main_window():
        vw = dpg.get_viewport_client_width()
        vh = dpg.get_viewport_client_height()
        dpg.set_item_width("main_win", vw)
        dpg.set_item_height("main_win", vh)

    dpg.set_viewport_resize_callback(fit_main_window)
    fit_main_window()  # apply immediately after show_viewport
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
