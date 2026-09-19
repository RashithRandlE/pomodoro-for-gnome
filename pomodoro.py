#!/usr/bin/env python3
"""
Pomodoro Timer — Floating pill-bar timer for GNOME / Wayland
GTK4 + Libadwaita  •  Task scoring  •  Achievements  •  Streaks
"""

import os
import sys

# Ensure X11/Xwayland backend is used on GNOME/Wayland to allow windows to stick
# to all virtual workspaces and stay always-on-top across the entire desktop.
if "GDK_BACKEND" not in os.environ and os.environ.get("DISPLAY"):
    os.environ["GDK_BACKEND"] = "x11"

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("GdkX11", "4.0")
    from gi.repository import GdkX11
    HAS_X11 = True
except (ValueError, ImportError):
    HAS_X11 = False

from gi.repository import Gtk, Adw, GLib, Gio, Gdk, Pango
import cairo
import json
import math
import time
import datetime
import uuid
import subprocess

# ─── Paths ───────────────────────────────────────────────────────────────────
DATA_DIR = os.path.expanduser("~/.local/share/pomodoro")
DATA_FILE = os.path.join(DATA_DIR, "data.json")
PRESETS = [25, 45, 60]

# ─── Achievements catalogue ─────────────────────────────────────────────────
ACHIEVEMENTS = [
    {"id": "first_pomo", "emoji": "🔥", "title": "First Pomodoro",
     "desc": "Complete your very first pomodoro"},
    {"id": "ten_daily", "emoji": "⚡", "title": "Power Day",
     "desc": "10 pomodoros in a single day"},
    {"id": "all_tasks", "emoji": "🎯", "title": "Clean Slate",
     "desc": "Complete every task on your list"},
    {"id": "streak_7", "emoji": "📅", "title": "Week Warrior",
     "desc": "7-day productive streak"},
    {"id": "streak_30", "emoji": "🏆", "title": "Monthly Master",
     "desc": "30-day productive streak"},
    {"id": "total_100", "emoji": "💯", "title": "Century Club",
     "desc": "100 lifetime pomodoros"},
    {"id": "zen_master", "emoji": "🧘", "title": "Zen Master",
     "desc": "Reach the Zen Master level"},
]

# ─── Level thresholds ────────────────────────────────────────────────────────
LEVELS = [
    (0, "Beginner"),
    (100, "Focused"),
    (500, "Productive"),
    (1000, "Dedicated"),
    (2000, "Master"),
    (5000, "Zen Master"),
]


def get_level(pts):
    """Return (index, title, points_into_level, points_to_next)."""
    for i in range(len(LEVELS) - 1, -1, -1):
        thr, title = LEVELS[i]
        if pts >= thr:
            nxt = LEVELS[i + 1][0] if i < len(LEVELS) - 1 else thr + 1
            return i, title, pts - thr, nxt - thr
    return 0, LEVELS[0][1], 0, LEVELS[1][0]


# ─── State colours (Cairo RGBA) ─────────────────────────────────────────────
STATE_COLORS = {
    "work": (0.91, 0.30, 0.24),
    "short_break": (0.15, 0.68, 0.38),
    "long_break": (0.16, 0.50, 0.73),
}

# ─── CSS ─────────────────────────────────────────────────────────────────────
CSS = """
/* Timer colours */
.timer-work   { color: #e74c3c; }
.timer-short  { color: #27ae60; }
.timer-long   { color: #2980b9; }

.timer-time {
    font-size: 38px;
    font-weight: 800;
    font-feature-settings: "tnum";
}
.session-label {
    font-size: 13px;
    font-weight: 600;
    opacity: 0.7;
}
.pause-warning {
    color: #f39c12;
    font-weight: 600;
}

/* Scores */
.score-value  { font-size: 18px; font-weight: 700; }
.level-title  { font-size: 16px; font-weight: 700; }
.level-bar    { min-height: 10px; border-radius: 5px; }

.achievement-badge  { font-size: 28px; padding: 6px; }
.achievement-locked { opacity: 0.25; }

/* Priority dots */
.priority-high   { color: #e74c3c; }
.priority-medium { color: #f39c12; }
.priority-low    { color: #27ae60; }

.active-task-label {
    font-size: 10px;
    opacity: 0.7;
}

/* ── Compact floating pill bar ──────────────────────── */
window.compact-win {
    background-color: transparent;
}

.compact-time {
    color: rgba(255,255,255,0.95);
    font-size: 14px;
    font-weight: 700;
    font-feature-settings: "tnum";
}
.compact-task {
    color: rgba(255,255,255,0.55);
    font-size: 11px;
}
.compact-sep {
    color: rgba(255,255,255,0.15);
    font-size: 12px;
}
.compact-btn {
    color: rgba(255,255,255,0.75);
    background: none;
    box-shadow: none;
    border: none;
    min-height: 24px;
    min-width: 24px;
    padding: 2px;
}
.compact-btn:hover {
    color: white;
    background: alpha(white, 0.12);
}

.big-mini-btn {
    padding: 10px 24px;
    margin-top: 14px;
    font-size: 14px;
    font-weight: 700;
    border-radius: 999px;
    background: alpha(@theme_selected_bg_color, 0.15);
    border: 1px solid alpha(@theme_selected_bg_color, 0.35);
}
.big-mini-btn:hover {
    background: alpha(@theme_selected_bg_color, 0.28);
}

.breath-btn {
    padding: 10px 20px;
    margin-top: 14px;
    font-size: 14px;
    font-weight: 700;
    border-radius: 999px;
    background: alpha(#2ecc71, 0.15);
    border: 1px solid alpha(#2ecc71, 0.35);
    color: #2ecc71;
}
.breath-btn:hover {
    background: alpha(#2ecc71, 0.28);
}
.breath-btn.active {
    background: alpha(#e74c3c, 0.15);
    border: 1px solid alpha(#e74c3c, 0.35);
    color: #e74c3c;
}

.compact-choice-btn {
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    padding: 3px 6px;
    min-height: 26px;
    box-shadow: none;
}

.main-choice-btn {
    padding: 10px 18px;
    font-size: 13px;
    font-weight: 700;
    border-radius: 999px;
}

.choice-breath {
    background: alpha(#2ecc71, 0.18);
    border: 1px solid alpha(#2ecc71, 0.45);
    color: #2ecc71;
}
.choice-breath:hover {
    background: alpha(#2ecc71, 0.32);
    color: #ffffff;
}

.choice-break {
    background: alpha(#3498db, 0.18);
    border: 1px solid alpha(#3498db, 0.45);
    color: #3498db;
}
.choice-break:hover {
    background: alpha(#3498db, 0.32);
    color: #ffffff;
}

.choice-next {
    background: alpha(#e74c3c, 0.18);
    border: 1px solid alpha(#e74c3c, 0.45);
    color: #e74c3c;
}
.choice-next:hover {
    background: alpha(#e74c3c, 0.32);
    color: #ffffff;
}
"""

# ─── Default data ────────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "work_duration": 25,
    "short_break": 5,
    "long_break": 15,
    "pause_budget": 120,
    "sound": True,
    "auto_start": False,
    "reset_daily": True,
    "auto_minimize": True,
    "box_breathing_breaks": True,
    "max_duration": 180,
}

DEFAULT_STATS = {
    "total_pomodoros": 0,
    "total_points": 0,
    "current_streak": 0,
    "last_active_date": "",
    "daily_pomodoros": 0,
    "daily_points": 0,
    "daily_tasks_completed": 0,
    "achievements": [],
}

DEFAULT_DATA = {
    "settings": dict(DEFAULT_SETTINGS),
    "tasks": [],
    "stats": dict(DEFAULT_STATS),
    "history": {},
}


# ─── Persistence ─────────────────────────────────────────────────────────────
class DataManager:
    @staticmethod
    def load():
        if not os.path.exists(DATA_FILE):
            return json.loads(json.dumps(DEFAULT_DATA))
        try:
            with open(DATA_FILE) as f:
                data = json.load(f)
            for section in ("settings", "stats"):
                if section not in data:
                    data[section] = dict(DEFAULT_DATA[section])
                else:
                    for k, v in DEFAULT_DATA[section].items():
                        data[section].setdefault(k, v)
            data.setdefault("tasks", [])
            data.setdefault("history", {})
            return data
        except Exception:
            return json.loads(json.dumps(DEFAULT_DATA))

    @staticmethod
    def save(data):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)


# ─── Cairo helper ────────────────────────────────────────────────────────────
def _pill(cr, x, y, w, h, r=None):
    """Draw a pill / rounded-rect path on *cr*."""
    if w <= 0 or h <= 0:
        return
    if r is None:
        r = h / 2
    r = min(r, w / 2, h / 2)
    d = math.pi / 180
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -90 * d, 0)
    cr.arc(x + w - r, y + h - r, r, 0, 90 * d)
    cr.arc(x + r, y + h - r, r, 90 * d, 180 * d)
    cr.arc(x + r, y + r, r, 180 * d, 270 * d)
    cr.close_path()


# ─── X11 / EWMH Window Manager Helper ─────────────────────────────────────────
class X11WindowManager:
    @staticmethod
    def pin_to_all_workspaces_and_top(window: Gtk.Window):
        """Pin window to appear on every virtual workspace and stay always on top."""
        try:
            surface = window.get_surface()
            if not surface or not hasattr(surface, "get_xid"):
                return False
            xid = surface.get_xid()
            if not xid:
                return False

            # 1. Send EWMH ClientMessages to the Root Window via libX11
            try:
                import ctypes
                from ctypes import Structure, Union, c_int, c_long, c_ulong, c_void_p, byref
                X11 = ctypes.CDLL("libX11.so.6")

                class _Data(Union):
                    _fields_ = [('b', ctypes.c_char * 20), ('s', ctypes.c_short * 10), ('l', ctypes.c_long * 5)]
                class XClientMessageEvent(Structure):
                    _fields_ = [
                        ('type', c_int), ('serial', c_ulong), ('send_event', c_int),
                        ('display', c_void_p), ('window', c_ulong), ('message_type', c_ulong),
                        ('format', c_int), ('data', _Data)
                    ]
                class XEvent(Union):
                    _fields_ = [('type', c_int), ('xclient', XClientMessageEvent), ('pad', c_long * 24)]

                dpy = X11.XOpenDisplay(None)
                if dpy:
                    root = X11.XDefaultRootWindow(dpy)
                    atom_state = X11.XInternAtom(dpy, b'_NET_WM_STATE', 0)
                    atom_sticky = X11.XInternAtom(dpy, b'_NET_WM_STATE_STICKY', 0)
                    atom_above = X11.XInternAtom(dpy, b'_NET_WM_STATE_ABOVE', 0)
                    atom_desktop = X11.XInternAtom(dpy, b'_NET_WM_DESKTOP', 0)
                    mask = (1 << 19) | (1 << 20)

                    # Add _NET_WM_STATE_STICKY and _NET_WM_STATE_ABOVE
                    ev_state = XEvent()
                    ev_state.type = 33
                    ev_state.xclient.window = xid
                    ev_state.xclient.message_type = atom_state
                    ev_state.xclient.format = 32
                    ev_state.xclient.data.l[0] = 1 # _NET_WM_STATE_ADD
                    ev_state.xclient.data.l[1] = atom_sticky
                    ev_state.xclient.data.l[2] = atom_above
                    ev_state.xclient.data.l[3] = 1
                    X11.XSendEvent(dpy, root, 0, mask, byref(ev_state))

                    # Set _NET_WM_DESKTOP to 0xFFFFFFFF (-1) for all workspaces
                    ev_desk = XEvent()
                    ev_desk.type = 33
                    ev_desk.xclient.window = xid
                    ev_desk.xclient.message_type = atom_desktop
                    ev_desk.xclient.format = 32
                    ev_desk.xclient.data.l[0] = -1
                    ev_desk.xclient.data.l[1] = 1
                    X11.XSendEvent(dpy, root, 0, mask, byref(ev_desk))

                    X11.XFlush(dpy)
                    X11.XCloseDisplay(dpy)
            except Exception:
                pass

            # 2. Also set properties directly via xprop if available
            try:
                subprocess.run(
                    ["xprop", "-id", hex(xid), "-f", "_NET_WM_STATE", "32a",
                     "-set", "_NET_WM_STATE", "_NET_WM_STATE_STICKY, _NET_WM_STATE_ABOVE"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                subprocess.run(
                    ["xprop", "-id", hex(xid), "-f", "_NET_WM_DESKTOP", "32c",
                     "-set", "_NET_WM_DESKTOP", "0xFFFFFFFF"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

            # 3. GdkX11Surface method
            if hasattr(surface, "move_to_desktop"):
                try:
                    surface.move_to_desktop(0xFFFFFFFF)
                except Exception:
                    pass

            return True
        except Exception:
            return False

    @staticmethod
    def move_to_current_workspace(window: Gtk.Window):
        """Move window to the current active workspace."""
        try:
            surface = window.get_surface()
            if not surface:
                return False
            if hasattr(surface, "move_to_current_desktop"):
                surface.move_to_current_desktop()
                return True
        except Exception:
            pass
        return False


# ─── Box Breathing Manager (4-4-4-4) ─────────────────────────────────────────
class BoxBreathingManager:
    PHASE_DURATION = 4.0
    CYCLE_DURATION = 16.0

    PHASES = [
        ("Inhale", (0.20, 0.78, 0.65), "( ˘▽˘ )", "Breathe in deeply..."),
        ("Hold",   (0.28, 0.65, 0.92), "( ˘◡˘ )", "Hold your breath..."),
        ("Exhale", (0.55, 0.45, 0.88), "( ˘o˘ )", "Slowly release..."),
        ("Hold",   (0.35, 0.75, 0.55), "( ◡‿◡ )", "Rest and be still..."),
    ]

    @classmethod
    def get_state(cls, start_time):
        now = time.time()
        elapsed = max(0.0, now - start_time)
        cycle_idx = int(elapsed // cls.CYCLE_DURATION) + 1
        pos = elapsed % cls.CYCLE_DURATION
        phase_idx = int(pos // cls.PHASE_DURATION)
        phase_pos = pos % cls.PHASE_DURATION
        sec_left = int(math.ceil(cls.PHASE_DURATION - phase_pos))
        frac = phase_pos / cls.PHASE_DURATION
        phase_name, color, face, instruction = cls.PHASES[phase_idx]

        if phase_idx == 0:
            scale = 0.5 - 0.5 * math.cos(frac * math.pi)
        elif phase_idx == 1:
            scale = 1.0 + 0.04 * math.sin(frac * 2 * math.pi)
        elif phase_idx == 2:
            scale = 0.5 + 0.5 * math.cos(frac * math.pi)
        else:
            scale = 0.0 + 0.04 * math.sin(frac * 2 * math.pi)

        return {
            "phase": phase_name,
            "phase_idx": phase_idx,
            "sec_left": sec_left,
            "frac": frac,
            "scale": scale,
            "color": color,
            "face": face,
            "instruction": instruction,
            "cycle": cycle_idx,
        }


# ═════════════════════════════════════════════════════════════════════════════
#  APPLICATION — state machine, scoring, notifications
# ═════════════════════════════════════════════════════════════════════════════
class PomodoroApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="org.randil.Pomodoro",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.data = DataManager.load()
        self._check_new_day()

        # Timer state
        self.state = "work"  # work | short_break | long_break
        self.session_count = 1  # 1-4
        self.is_running = False
        self.time_left = self.data["settings"]["work_duration"] * 60
        self._timer_id = None
        self.active_task_id = None

        # Pause state
        self.is_paused = False
        self.pause_used = 0
        self._pause_id = None

        # Box Breathing & Fluid Animation state
        self.box_breathing_active = False
        self.breath_start_time = 0.0
        self._anim_id = None

        # Windows
        self._main_win = None
        self._compact_win = None

        # Completion prompt state (when pomodoro finishes)
        self.pending_choice = False

    # ── daily reset ──────────────────────────────────────────────────────
    def _check_new_day(self):
        today = str(datetime.date.today())
        last = self.data["stats"].get("last_active_date", "")
        if last == today:
            return
        if last:
            self.data["history"][last] = {
                "pomodoros": self.data["stats"]["daily_pomodoros"],
                "points": self.data["stats"]["daily_points"],
                "tasks": self.data["stats"]["daily_tasks_completed"],
            }
            try:
                gap = (datetime.date.today()
                       - datetime.date.fromisoformat(last)).days
                if gap == 1 and self.data["stats"]["daily_pomodoros"] >= 4:
                    self.data["stats"]["current_streak"] += 1
                    bonus = 20 * self.data["stats"]["current_streak"]
                    self.data["stats"]["total_points"] += bonus
                elif gap > 1:
                    self.data["stats"]["current_streak"] = 0
            except Exception:
                self.data["stats"]["current_streak"] = 0
        self.data["stats"].update(
            daily_pomodoros=0, daily_points=0,
            daily_tasks_completed=0, last_active_date=today,
        )
        if self.data["settings"]["reset_daily"]:
            self.data["tasks"] = [
                t for t in self.data["tasks"] if not t.get("completed")
            ]
        DataManager.save(self.data)

    # ── activation ───────────────────────────────────────────────────────
    def do_activate(self):
        display = Gdk.Display.get_default()
        if display:
            icon_theme = Gtk.IconTheme.get_for_display(display)
            icon_theme.add_search_path(DATA_DIR)
            icon_theme.add_search_path(os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps"))
        Gtk.Window.set_default_icon_name("pomodoro")

        if not self._main_win:
            css = Gtk.CssProvider()
            css.load_from_string(CSS)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            self._main_win = MainWindow(self)
            self._compact_win = CompactWindow(self)
        self._main_win.present()
        self._refresh_all()

    # ── helpers ──────────────────────────────────────────────────────────
    def duration_for(self, state):
        s = self.data["settings"]
        return {
            "work": s["work_duration"],
            "short_break": s["short_break"],
            "long_break": s["long_break"],
        }[state] * 60

    # ── timer controls ───────────────────────────────────────────────────
    def start_timer(self):
        self.pending_choice = False
        if self.is_running:
            return
        # resume from pause
        if self.is_paused:
            self.is_paused = False
            if self._pause_id:
                GLib.source_remove(self._pause_id)
                self._pause_id = None
        self.is_running = True
        self._timer_id = GLib.timeout_add(1000, self._tick)
        self._ensure_anim()
        self._refresh_controls()

    def pause_timer(self):
        if not self.is_running:
            return
        self.is_running = False
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        # start pause budget countdown only during work
        if self.state == "work":
            self.is_paused = True
            self._pause_id = GLib.timeout_add(1000, self._pause_tick)
        self._check_stop_anim()
        self._refresh_controls()

    def abandon_session(self):
        """Give up the current work session. −15 pts."""
        self.pending_choice = False
        self._stop_all()
        self.stop_box_breathing()
        self.is_paused = False
        self._add_points(-15)
        self._notify("Session abandoned",
                     "−15 points. You'll get it next time! 💪")
        self.time_left = self.duration_for("work")
        self.pause_used = 0
        self._refresh_all()

    def skip_break(self):
        """End the current break early (no penalty)."""
        if self.state not in ("short_break", "long_break"):
            return
        self.pending_choice = False
        self._stop_all()
        self.stop_box_breathing()
        self._advance_after_break()

    def _stop_all(self):
        self.is_running = False
        for attr in ("_timer_id", "_pause_id"):
            sid = getattr(self, attr)
            if sid:
                GLib.source_remove(sid)
                setattr(self, attr, None)
        self._check_stop_anim()

    # ── box breathing & animation ─────────────────────────────────────────
    def start_box_breathing(self):
        self.box_breathing_active = True
        self.breath_start_time = time.time()
        self._ensure_anim()
        self._refresh_all()

    def stop_box_breathing(self):
        self.box_breathing_active = False
        self._check_stop_anim()
        self._refresh_all()

    def toggle_box_breathing(self):
        if self.box_breathing_active:
            self.stop_box_breathing()
        else:
            self.start_box_breathing()

    def _ensure_anim(self):
        if self._anim_id is None:
            self._anim_id = GLib.timeout_add(33, self._on_anim_frame)

    def _check_stop_anim(self):
        if not self.is_running and not self.box_breathing_active:
            if self._anim_id is not None:
                GLib.source_remove(self._anim_id)
                self._anim_id = None

    def _on_anim_frame(self):
        if not self.is_running and not self.box_breathing_active:
            self._anim_id = None
            return False
        if self._main_win and self._main_win.get_visible():
            self._main_win._timer_da.queue_draw()
            if self.box_breathing_active:
                self._main_win.refresh_breath_labels()
        if self._compact_win and self._compact_win.get_visible():
            self._compact_win._canvas.queue_draw()
            if self.box_breathing_active:
                self._compact_win.refresh_breath_labels()
        return True

    # ── ticks ────────────────────────────────────────────────────────────
    def _tick(self):
        if not self.is_running:
            return False
        self.time_left -= 1
        if self.time_left <= 0:
            self.time_left = 0
            self._session_finished()
            return False
        self._refresh_timer()
        return True

    def _pause_tick(self):
        if not self.is_paused:
            return False
        self.pause_used += 1
        budget = self.data["settings"]["pause_budget"]
        if self.pause_used >= budget:
            self._stop_all()
            self.stop_box_breathing()
            self.is_paused = False
            self._add_points(-15)
            self._notify("⏸ Pause expired",
                         "Auto-abandoned — you exceeded the pause budget. −15 pts.")
            self.time_left = self.duration_for("work")
            self.pause_used = 0
            self._refresh_all()
            return False
        self._refresh_controls()
        return True

    # ── session lifecycle ────────────────────────────────────────────────
    def _session_finished(self):
        self._stop_all()
        self._play_sound()

        if self.state == "work":
            self._add_points(10)
            self.data["stats"]["total_pomodoros"] += 1
            self.data["stats"]["daily_pomodoros"] += 1
            self.pause_used = 0

            if self.active_task_id:
                for t in self.data["tasks"]:
                    if t["id"] == self.active_task_id:
                        t["actual_pomos"] = t.get("actual_pomos", 0) + 1
                        break

            self._check_achievements()

            self.stop_box_breathing()
            self.pending_choice = True
            self._notify("Pomodoro complete! 🍅",
                         f"Session {self.session_count}/4 done — choose what's next!")
            DataManager.save(self.data)
            self._refresh_all()
        else:
            self._advance_after_break()

    def choose_breathing(self):
        """Start a guided box breathing break session."""
        self.pending_choice = False
        if self.session_count >= 4:
            self.state = "long_break"
            self.session_count = 0
            title = "Long break! 🫁"
            body = "4 sessions done — relax with Box Breathing."
        else:
            self.state = "short_break"
            title = "Short break! 🫁"
            body = f"Session {self.session_count}/4 complete — breathe & relax."
        self.time_left = self.duration_for(self.state)
        self.start_box_breathing()
        self.start_timer()
        self._notify(title, body)
        DataManager.save(self.data)
        self._refresh_all()

    def choose_break(self):
        """Start a regular break timer without breathing animation."""
        self.pending_choice = False
        self.stop_box_breathing()
        if self.session_count >= 4:
            self.state = "long_break"
            self.session_count = 0
            title = "Long break! ☕"
            body = "4 sessions done — take a well-earned rest."
        else:
            self.state = "short_break"
            title = "Short break! ☕"
            body = f"Session {self.session_count}/4 complete."
        self.time_left = self.duration_for(self.state)
        self.start_timer()
        self._notify(title, body)
        DataManager.save(self.data)
        self._refresh_all()

    def choose_next_session(self):
        """Skip break and start the next pomodoro work session immediately."""
        self.pending_choice = False
        self.stop_box_breathing()
        if self.session_count >= 4:
            self.session_count = 1
        else:
            self.session_count += 1
        self.state = "work"
        self.pause_used = 0
        self.time_left = self.duration_for("work")
        self.start_timer()
        self._notify("Back to work! 🍅", "Next session started — let's focus!")
        DataManager.save(self.data)
        self._refresh_all()

    def _advance_after_break(self):
        self.pending_choice = False
        self.stop_box_breathing()
        self.state = "work"
        self.session_count += 1
        self.pause_used = 0
        self.time_left = self.duration_for("work")
        self._notify("Back to work! 🍅", "Break over — let's focus.")
        DataManager.save(self.data)
        self._refresh_all()
        if self.data["settings"]["auto_start"]:
            self.start_timer()

    # ── scoring ──────────────────────────────────────────────────────────
    def _add_points(self, pts):
        self.data["stats"]["total_points"] = max(
            0, self.data["stats"]["total_points"] + pts
        )
        self.data["stats"]["daily_points"] += pts
        DataManager.save(self.data)

    def complete_task(self, task):
        self._add_points(25)
        self.data["stats"]["daily_tasks_completed"] += 1
        if self.data["tasks"] and all(
            t.get("completed") for t in self.data["tasks"]
        ):
            self._add_points(50)
            self._unlock("all_tasks")
            self._notify("🎯 All tasks done!", "+50 bonus points!")
        self._check_achievements()
        DataManager.save(self.data)

    def _unlock(self, aid):
        achs = self.data["stats"]["achievements"]
        if aid not in achs:
            achs.append(aid)
            for a in ACHIEVEMENTS:
                if a["id"] == aid:
                    self._notify(f'{a["emoji"]} Achievement!', a["title"])

    def _check_achievements(self):
        s = self.data["stats"]
        if s["total_pomodoros"] >= 1:
            self._unlock("first_pomo")
        if s["daily_pomodoros"] >= 10:
            self._unlock("ten_daily")
        if s["current_streak"] >= 7:
            self._unlock("streak_7")
        if s["current_streak"] >= 30:
            self._unlock("streak_30")
        if s["total_pomodoros"] >= 100:
            self._unlock("total_100")
        if get_level(s["total_points"])[0] >= len(LEVELS) - 1:
            self._unlock("zen_master")

    # ── sound / notification ─────────────────────────────────────────────
    def _play_sound(self):
        if not self.data["settings"]["sound"]:
            return
        for p in (
            "/usr/share/sounds/freedesktop/stereo/complete.oga",
            "/usr/share/sounds/freedesktop/stereo/bell.oga",
        ):
            if os.path.exists(p):
                try:
                    subprocess.Popen(
                        ["paplay", p],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except FileNotFoundError:
                    pass
                break

    def _notify(self, title, body):
        icon_path = os.path.join(DATA_DIR, "pomodoro.svg")
        icon_arg = icon_path if os.path.exists(icon_path) else "pomodoro"
        try:
            subprocess.Popen(
                ["notify-send", "-i", icon_arg,
                 "-a", "Pomodoro", title, body],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    # ── mode switching ───────────────────────────────────────────────────
    def show_compact(self):
        if self._main_win:
            self._main_win._ignore_focus_change = True
            self._main_win.set_visible(False)
        if self._compact_win:
            self._compact_win.set_visible(True)
            self._compact_win.present()
            self._compact_win.try_pin_above()
            GLib.timeout_add(100, self._compact_win.try_pin_above)
            GLib.timeout_add(300, self._compact_win.try_pin_above)
            GLib.timeout_add(800, self._compact_win.try_pin_above)

    def show_expanded(self):
        if self._compact_win:
            self._compact_win.set_visible(False)
        if self._main_win:
            self._main_win._ignore_focus_change = True
            self._main_win.set_visible(True)
            self._main_win.present()
            X11WindowManager.move_to_current_workspace(self._main_win)
            self._refresh_all()
            GLib.timeout_add(1200, lambda: setattr(self._main_win, "_ignore_focus_change", False) or False)

    # ── UI refresh ───────────────────────────────────────────────────────
    def _refresh_timer(self):
        if self._main_win:
            self._main_win.refresh_timer()
        if self._compact_win:
            self._compact_win.refresh()
            if self._compact_win.get_visible():
                self._compact_win.try_pin_above()

    def _refresh_controls(self):
        if self._main_win:
            self._main_win.refresh_controls()
        if self._compact_win:
            self._compact_win.refresh()

    def _refresh_all(self):
        if self._main_win:
            self._main_win.refresh_timer()
            self._main_win.refresh_controls()
            self._main_win.refresh_state_label()
            self._main_win.refresh_tasks()
            self._main_win.refresh_stats()
            self._main_win.update_presets()
        if self._compact_win:
            self._compact_win.refresh()


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW  — expanded view with four tab pages
# ═════════════════════════════════════════════════════════════════════════════
class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Pomodoro Timer")
        self.app = app
        self.set_default_size(420, 640)
        self.set_icon_name("pomodoro")
        self._updating = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(box)

        # Header
        header = Adw.HeaderBar()
        app_icon = Gtk.Image.new_from_icon_name("pomodoro")
        app_icon.set_pixel_size(24)
        app_icon.set_margin_start(8)
        header.pack_start(app_icon)

        compact_btn = Gtk.Button(
            icon_name="window-minimize-symbolic",
            tooltip_text="Floating mini timer",
        )
        compact_btn.connect("clicked", lambda _: self.app.show_compact())
        header.pack_end(compact_btn)

        self._vs = Adw.ViewStack()
        sw = Adw.ViewSwitcher(stack=self._vs,
                              policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(sw)
        box.append(header)

        self._build_timer_page()
        self._build_tasks_page()
        self._build_stats_page()
        self._build_settings_page()

        box.append(self._vs)

        self.connect("close-request", self._on_close)

        # Auto-minimize when window loses focus (switched away)
        self._auto_compact_id = None
        self._ignore_focus_change = True
        GLib.timeout_add(1500, self._enable_auto_compact)
        self.connect("notify::is-active", self._on_focus_change)

    def _enable_auto_compact(self):
        self._ignore_focus_change = False
        return False

    def _on_focus_change(self, *_args):
        if getattr(self, "_ignore_focus_change", False) or not self.get_visible():
            return
        if not self.is_active():
            if self.app.data["settings"].get("auto_minimize", True):
                if self._auto_compact_id is None:
                    self._auto_compact_id = GLib.timeout_add(
                        350, self._do_auto_compact,
                    )
        else:
            if self._auto_compact_id is not None:
                GLib.source_remove(self._auto_compact_id)
                self._auto_compact_id = None

    def _do_auto_compact(self):
        self._auto_compact_id = None
        if self.get_visible() and not self.is_active() and not getattr(self, "_ignore_focus_change", False):
            if self.app.data["settings"].get("auto_minimize", True):
                self.app.show_compact()
        return False

    def _on_close(self, _w):
        if self.app._compact_win:
            self.app._compact_win.destroy()
        self.app.quit()
        return False

    # ── Timer page ───────────────────────────────────────────────────────
    def _build_timer_page(self):
        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=10,
            margin_top=12, margin_bottom=16,
            margin_start=24, margin_end=24, vexpand=True,
        )

        # state label
        self._state_lbl = Gtk.Label(css_classes=["session-label"])
        page.append(self._state_lbl)

        # preset buttons
        row = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER,
                      margin_bottom=2)
        row.append(Gtk.Label(label="Focus", css_classes=["dim-label", "caption"],
                             margin_end=4))
        linked = Gtk.Box(css_classes=["linked"])
        self._preset_btns = {}
        for m in PRESETS:
            b = Gtk.Button(label=f"{m}")
            b.connect("clicked", self._on_preset, m)
            linked.append(b)
            self._preset_btns[m] = b
        self._custom_btn = Gtk.Button(label="Custom")
        self._custom_btn.connect("clicked", self._on_custom_clicked)
        linked.append(self._custom_btn)
        row.append(linked)
        row.append(Gtk.Label(label="min", css_classes=["dim-label", "caption"],
                             margin_start=4))
        page.append(row)

        # timer ring with interactive draggable dial
        self._timer_da = Gtk.DrawingArea()
        self._timer_da.set_size_request(240, 240)
        self._timer_da.set_halign(Gtk.Align.CENTER)
        self._timer_da.set_draw_func(self._draw_ring)
        self._setup_dial_controller()

        ov = Gtk.Overlay()
        ov.set_child(self._timer_da)
        ctr = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                      halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                      spacing=2)
        ctr.set_can_target(False)
        self._time_lbl = Gtk.Label(
            label="25:00", css_classes=["timer-time", "timer-work"],
        )
        ctr.append(self._time_lbl)
        self._active_lbl = Gtk.Label(
            css_classes=["active-task-label"],
            ellipsize=Pango.EllipsizeMode.END, max_width_chars=18,
        )
        ctr.append(self._active_lbl)
        ov.add_overlay(ctr)
        page.append(ov)

        # controls row
        self._ctrls = Gtk.Box(spacing=14, halign=Gtk.Align.CENTER)

        self._act_btn = Gtk.Button(css_classes=["circular"])
        self._act_btn.set_size_request(44, 44)
        self._act_btn.connect("clicked", self._on_action)
        self._ctrls.append(self._act_btn)

        self._play_btn = Gtk.Button(
            icon_name="media-playback-start-symbolic",
            css_classes=["circular", "suggested-action"],
        )
        self._play_btn.set_size_request(56, 56)
        self._play_btn.connect("clicked", self._on_play_pause)
        self._ctrls.append(self._play_btn)

        page.append(self._ctrls)

        # Choice row when pomodoro ends
        self._choice_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
            halign=Gtk.Align.CENTER, margin_top=4, margin_bottom=4,
            visible=False,
        )

        self._main_breath_btn = Gtk.Button(
            label="🫁 Breathing Session",
            css_classes=["main-choice-btn", "choice-breath"],
            tooltip_text="Start a 4-4-4-4 Box Breathing relaxation",
        )
        self._main_breath_btn.connect("clicked", lambda _: self.app.choose_breathing())
        self._choice_box.append(self._main_breath_btn)

        self._main_break_btn = Gtk.Button(
            label="☕ 5m Break",
            css_classes=["main-choice-btn", "choice-break"],
            tooltip_text="Start a 5-minute break timer",
        )
        self._main_break_btn.connect("clicked", lambda _: self.app.choose_break())
        self._choice_box.append(self._main_break_btn)

        self._main_next_btn = Gtk.Button(
            label="🍅 Next Session",
            css_classes=["main-choice-btn", "choice-next"],
            tooltip_text="Start the next Pomodoro focus session",
        )
        self._main_next_btn.connect("clicked", lambda _: self.app.choose_next_session())
        self._choice_box.append(self._main_next_btn)

        page.append(self._choice_box)

        # pause budget label
        self._pause_lbl = Gtk.Label(
            visible=False, css_classes=["pause-warning", "caption"],
        )
        page.append(self._pause_lbl)

        # Action buttons row: Box Breathing & Floating Mini Mode
        act_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
            halign=Gtk.Align.CENTER, margin_top=6,
        )

        # Box Breathing button
        self._breath_btn = Gtk.Button(
            label="🫁 Box Breathing",
            css_classes=["pill", "breath-btn"],
            tooltip_text="Toggle 4-4-4-4 Box Breathing relaxation",
        )
        self._breath_btn.connect("clicked", lambda _: self.app.toggle_box_breathing())
        act_row.append(self._breath_btn)

        # Big minimize button to switch to floating mini mode
        mini_btn_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
            halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
        )
        mini_icon = Gtk.Image.new_from_icon_name("window-minimize-symbolic")
        mini_icon.set_pixel_size(18)
        mini_lbl = Gtk.Label(label="Floating Mini")
        mini_lbl.add_css_class("heading")
        mini_btn_box.append(mini_icon)
        mini_btn_box.append(mini_lbl)

        self._big_mini_btn = Gtk.Button(
            child=mini_btn_box,
            css_classes=["pill", "big-mini-btn"],
            tooltip_text="Switch to draggable floating mini timer bar",
        )
        self._big_mini_btn.connect("clicked", lambda _: self.app.show_compact())
        act_row.append(self._big_mini_btn)

        page.append(act_row)

        self._vs.add_titled_with_icon(page, "timer", "Timer",
                                      "alarm-symbolic")

    # ── Tasks page ───────────────────────────────────────────────────────
    def _build_tasks_page(self):
        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
            margin_top=8, margin_bottom=8,
            margin_start=10, margin_end=10, vexpand=True,
        )
        # add-task row
        ar = Gtk.Box(spacing=6)
        self._task_entry = Gtk.Entry(
            placeholder_text="What will you work on?", hexpand=True,
        )
        self._task_entry.connect("activate", self._on_add_task)
        ar.append(self._task_entry)
        self._pomo_spin = Gtk.SpinButton.new_with_range(1, 8, 1)
        self._pomo_spin.set_value(1)
        self._pomo_spin.set_tooltip_text("Estimated pomodoros")
        ar.append(self._pomo_spin)
        self._prio_dd = Gtk.DropDown.new_from_strings(
            ["High", "Medium", "Low"]
        )
        self._prio_dd.set_selected(1)
        self._prio_dd.set_tooltip_text("Priority")
        ar.append(self._prio_dd)
        add_btn = Gtk.Button(
            icon_name="list-add-symbolic",
            css_classes=["suggested-action"],
        )
        add_btn.connect("clicked", self._on_add_task)
        ar.append(add_btn)
        page.append(ar)

        self._task_list = Gtk.ListBox(
            selection_mode=Gtk.SelectionMode.NONE,
            css_classes=["boxed-list"],
        )
        scr = Gtk.ScrolledWindow(vexpand=True, child=self._task_list)
        page.append(scr)

        clr = Gtk.Button(
            label="Clear completed", css_classes=["destructive-action"],
        )
        clr.connect("clicked", self._on_clear)
        page.append(clr)

        self._vs.add_titled_with_icon(page, "tasks", "Tasks",
                                      "view-list-symbolic")

    # ── Stats page ───────────────────────────────────────────────────────
    def _build_stats_page(self):
        inner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            margin_top=16, margin_bottom=16,
            margin_start=20, margin_end=20, vexpand=True,
        )
        # level card
        card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6,
            css_classes=["card"],
        )
        ci = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6,
            margin_top=16, margin_bottom=16,
            margin_start=16, margin_end=16,
        )
        self._lvl_lbl = Gtk.Label(
            css_classes=["level-title"], halign=Gtk.Align.START,
        )
        ci.append(self._lvl_lbl)
        self._lvl_bar = Gtk.ProgressBar(css_classes=["level-bar"])
        ci.append(self._lvl_bar)
        self._lvl_det = Gtk.Label(
            halign=Gtk.Align.START, css_classes=["dim-label", "caption"],
        )
        ci.append(self._lvl_det)
        card.append(ci)
        inner.append(card)

        # stat rows
        grp = Adw.PreferencesGroup(title="Today")
        self._srows = {}
        for key, label in [
            ("daily_pomodoros", "Pomodoros"),
            ("daily_tasks_completed", "Tasks completed"),
            ("daily_points", "Points earned"),
            ("current_streak", "Day streak 🔥"),
            ("total_points", "Lifetime score"),
            ("total_pomodoros_all", "Lifetime pomodoros"),
        ]:
            r = Adw.ActionRow(title=label)
            v = Gtk.Label(
                label="0", css_classes=["score-value"],
                valign=Gtk.Align.CENTER,
            )
            r.add_suffix(v)
            grp.add(r)
            self._srows[key] = v
        inner.append(grp)

        # achievements
        agrp = Adw.PreferencesGroup(title="Achievements")
        self._ach_flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            max_children_per_line=7, min_children_per_line=4,
            homogeneous=True,
        )
        agrp.add(self._ach_flow)
        inner.append(agrp)

        scr = Gtk.ScrolledWindow(vexpand=True, child=inner)
        self._vs.add_titled_with_icon(scr, "stats", "Stats",
                                      "starred-symbolic")

    # ── Settings page ────────────────────────────────────────────────────
    def _build_settings_page(self):
        prefs = Adw.PreferencesPage()

        g1 = Adw.PreferencesGroup(title="Timer Durations (minutes)")
        max_d = self.app.data["settings"].get("max_duration", 180)
        self._max_spin = self._settings_row(
            g1, "Max dial limit", 30, 360, max_d,
        )
        self._w_spin = self._settings_row(
            g1, "Work session", 1, max_d,
            self.app.data["settings"]["work_duration"],
        )
        self._sb_spin = self._settings_row(
            g1, "Short break", 1, 30,
            self.app.data["settings"]["short_break"],
        )
        self._lb_spin = self._settings_row(
            g1, "Long break", 5, 60,
            self.app.data["settings"]["long_break"],
        )
        prefs.add(g1)

        g2 = Adw.PreferencesGroup(title="Pause Budget")
        self._pb_spin = self._settings_row(
            g2, "Max pause per session (min)", 1, 10,
            self.app.data["settings"]["pause_budget"] // 60,
        )
        prefs.add(g2)

        g3 = Adw.PreferencesGroup(title="Behaviour")
        self._snd_sw = self._switch_row(
            g3, "Sound effects", "Play a sound when sessions end",
            self.app.data["settings"]["sound"],
        )
        self._auto_sw = self._switch_row(
            g3, "Auto-start next", "Begin the next session automatically",
            self.app.data["settings"]["auto_start"],
        )
        self._rst_sw = self._switch_row(
            g3, "Reset tasks daily",
            "Remove completed tasks each new day",
            self.app.data["settings"]["reset_daily"],
        )
        self._auto_min_sw = self._switch_row(
            g3, "Auto-minimize on window switch",
            "Automatically shrink to floating mini bar when switching windows",
            self.app.data["settings"].get("auto_minimize", True),
        )
        self._breath_sw = self._switch_row(
            g3, "Box breathing during breaks",
            "Guide 4-4-4-4 breathing during short and long breaks",
            self.app.data["settings"].get("box_breathing_breaks", True),
        )
        prefs.add(g3)

        scr = Gtk.ScrolledWindow(vexpand=True, child=prefs)
        self._vs.add_titled_with_icon(scr, "settings", "Settings",
                                      "emblem-system-symbolic")

    def _settings_row(self, group, title, lo, hi, val):
        spin = Gtk.SpinButton.new_with_range(lo, hi, 1)
        spin.set_value(val)
        spin.set_valign(Gtk.Align.CENTER)
        spin.connect("value-changed", self._on_settings)
        row = Adw.ActionRow(title=title)
        row.add_suffix(spin)
        group.add(row)
        return spin

    def _switch_row(self, group, title, subtitle, active):
        sw = Gtk.Switch(valign=Gtk.Align.CENTER)
        sw.set_active(active)
        sw.connect("notify::active", self._on_settings)
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        row.add_suffix(sw)
        row.set_activatable_widget(sw)
        group.add(row)
        return sw

    # ── drawing ──────────────────────────────────────────────────────────
    def _draw_ring(self, _a, cr, w, h):
        if self.app.box_breathing_active:
            self._draw_box_breathing(cr, w, h)
            return

        xc, yc = w / 2, h / 2
        radius = 86
        if self.app.pending_choice:
            cr.set_line_width(8)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.arc(xc, yc, radius, 0, 2 * math.pi)
            cr.set_source_rgba(0.95, 0.65, 0.20, 0.90)
            cr.stroke()
            return

        max_d = self.app.data["settings"].get("max_duration", 180)
        cur_work_mins = self.app.data["settings"].get("work_duration", 25)
        r, g, b = STATE_COLORS.get(self.app.state, (0.5, 0.5, 0.5))

        # ── 1. Outer dial bezel & tick marks ──────────────────────────────
        step = 15 if max_d <= 180 else 30
        cr.set_line_width(1.5)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(9)

        for m in range(step, max_d + 1, step):
            angle = -math.pi / 2 + 2 * math.pi * (m / max_d)
            is_major = (m % 30 == 0)
            r_in = radius + 8
            r_out = radius + (14 if is_major else 11)
            cr.move_to(xc + r_in * math.cos(angle), yc + r_in * math.sin(angle))
            cr.line_to(xc + r_out * math.cos(angle), yc + r_out * math.sin(angle))
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.35 if is_major else 0.15)
            cr.stroke()

            if is_major and m < max_d:
                txt = f"{m}"
                xb, yb, tw, th, _, _ = cr.text_extents(txt)
                tx = xc + (radius + 22) * math.cos(angle) - tw / 2
                ty = yc + (radius + 22) * math.sin(angle) + th / 2
                cr.move_to(tx, ty)
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.40)
                cr.show_text(txt)

        # ── 2. Background circular ring track ─────────────────────────────
        cr.set_line_width(8)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.arc(xc, yc, radius, 0, 2 * math.pi)
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.15)
        cr.stroke()

        # ── 3. Progress / Duration arc ────────────────────────────────────
        start = -math.pi / 2
        if self.app.is_running:
            full = self.app.duration_for(self.app.state)
            progress = (full - self.app.time_left) / full if full > 0 else 0
            if progress > 0.001:
                end = start + 2 * math.pi * progress
                cr.set_line_width(8)
                cr.set_source_rgba(r, g, b, 0.90)
                cr.arc(xc, yc, radius, start, end)
                cr.stroke()

                # Subtle liquid tip glint
                t = time.time()
                hx = xc + radius * math.cos(end)
                hy = yc + radius * math.sin(end)
                tip_r = 4.0 + 0.6 * math.sin(t * 2.5)
                cr.arc(hx, hy, tip_r, 0, 2 * math.pi)
                cr.set_source_rgba(min(1.0, r + 0.25), min(1.0, g + 0.25), min(1.0, b + 0.25), 0.95)
                cr.fill()
        else:
            # When idle / paused / setting time: show set duration arc and draggable knob
            frac = min(1.0, max(0.005, cur_work_mins / max_d))
            end = start + 2 * math.pi * frac
            cr.set_line_width(8)
            cr.set_source_rgba(r, g, b, 0.85)
            cr.arc(xc, yc, radius, start, end)
            cr.stroke()

            # ── 4. Draggable Knob Handle ──────────────────────────────────
            kx = xc + radius * math.cos(end)
            ky = yc + radius * math.sin(end)

            is_active = getattr(self, "_is_dragging_dial", False)
            is_hover = getattr(self, "_dial_hover", False)
            aura_r = 13.0 if (is_active or is_hover) else 10.0
            aura_alpha = 0.40 if is_active else (0.25 if is_hover else 0.12)

            # Glowing halo
            cr.arc(kx, ky, aura_r, 0, 2 * math.pi)
            cr.set_source_rgba(r, g, b, aura_alpha)
            cr.fill()

            # Dark rim
            cr.arc(kx, ky, 8.5, 0, 2 * math.pi)
            cr.set_source_rgba(0.08, 0.08, 0.12, 0.95)
            cr.fill()

            # Bright face
            cr.arc(kx, ky, 7.0, 0, 2 * math.pi)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
            cr.fill()

            # Inner accent pip
            cr.arc(kx, ky, 3.2, 0, 2 * math.pi)
            cr.set_source_rgba(r, g, b, 1.0)
            cr.fill()

    def _draw_box_breathing(self, cr, w, h):
        st = BoxBreathingManager.get_state(self.app.breath_start_time)
        xc, yc = w / 2, h / 2
        R = min(w, h) / 2 - 12

        # 1. Outer Rounded Box track & active side
        box_size = R * 1.8
        bx = xc - box_size / 2
        by = yc - box_size / 2
        br = 18

        cr.save()
        _pill(cr, bx, by, box_size, box_size, br)
        cr.set_line_width(4)
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.15)
        cr.stroke()

        # Active edge of the box
        cr.set_line_width(6)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        r, g, b = st["color"]
        cr.set_source_rgba(r, g, b, 0.95)
        f = st["frac"]

        if st["phase_idx"] == 0:  # Top: Inhale (left to right)
            cr.move_to(bx + br, by)
            cr.line_to(bx + br + (box_size - 2 * br) * f, by)
            cr.stroke()
        elif st["phase_idx"] == 1:  # Right: Hold (top to bottom)
            cr.move_to(bx + box_size, by + br)
            cr.line_to(bx + box_size, by + br + (box_size - 2 * br) * f)
            cr.stroke()
        elif st["phase_idx"] == 2:  # Bottom: Exhale (right to left)
            cr.move_to(bx + box_size - br, by + box_size)
            cr.line_to(bx + box_size - br - (box_size - 2 * br) * f, by + box_size)
            cr.stroke()
        else:  # Left: Hold (bottom to top)
            cr.move_to(bx, by + box_size - br)
            cr.line_to(bx, by + box_size - br - (box_size - 2 * br) * f)
            cr.stroke()
        cr.restore()

        # 2. Central expanding & contracting pulsing bubble
        r_min = R * 0.38
        r_max = R * 0.72
        cur_r = r_min + (r_max - r_min) * st["scale"]

        # Outer gentle pulsing aura rings
        for aura_r, aura_alpha in [(cur_r + 14, 0.07), (cur_r + 7, 0.15)]:
            cr.arc(xc, yc, max(1, aura_r), 0, 2 * math.pi)
            cr.set_source_rgba(r, g, b, aura_alpha)
            cr.fill()

        # Main pulsing bubble
        cr.arc(xc, yc, max(1, cur_r), 0, 2 * math.pi)
        cr.set_source_rgba(r, g, b, 0.32 + 0.15 * st["scale"])
        cr.fill_preserve()
        cr.set_source_rgba(r, g, b, 0.85)
        cr.set_line_width(3.5)
        cr.stroke()

        # 3. Draw cute face inside bubble
        cr.save()
        cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(24)
        face = st["face"]
        xbear, ybear, tw, th, _, _ = cr.text_extents(face)
        cr.move_to(xc - tw / 2, yc - 2)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
        cr.show_text(face)

        # 4. Phase and countdown below face
        cr.set_font_size(13)
        sub = f"{st['phase'].upper()}  {st['sec_left']}s"
        xbear, ybear, tw, th, _, _ = cr.text_extents(sub)
        cr.move_to(xc - tw / 2, yc + 22)
        cr.set_source_rgba(r, g, b, 1.0)
        cr.show_text(sub)
        cr.restore()

    # ── dial controller ──────────────────────────────────────────────────
    def _setup_dial_controller(self):
        self._is_dragging_dial = False
        self._dial_hover = False

        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self._on_dial_drag_begin)
        drag.connect("drag-update", self._on_dial_drag_update)
        drag.connect("drag-end", self._on_dial_drag_end)
        self._timer_da.add_controller(drag)

        motion = Gtk.EventControllerMotion.new()
        motion.connect("motion", self._on_dial_motion)
        motion.connect("leave", self._on_dial_leave)
        self._timer_da.add_controller(motion)

    def _on_dial_motion(self, _controller, x, y):
        w = self._timer_da.get_width()
        h = self._timer_da.get_height()
        xc, yc = w / 2, h / 2
        dist = math.hypot(x - xc, y - yc)
        radius = 86
        near = (radius - 22 <= dist <= radius + 32)
        if near != self._dial_hover:
            self._dial_hover = near
            self._timer_da.set_cursor_from_name("grab" if near else "default")
            self._timer_da.queue_draw()

    def _on_dial_leave(self, _controller):
        if self._dial_hover:
            self._dial_hover = False
            self._timer_da.set_cursor_from_name("default")
            self._timer_da.queue_draw()

    def _on_dial_drag_begin(self, gesture, start_x, start_y):
        if self.app.box_breathing_active or self.app.pending_choice:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return

        w = self._timer_da.get_width()
        h = self._timer_da.get_height()
        xc, yc = w / 2, h / 2
        dist = math.hypot(start_x - xc, start_y - yc)
        radius = 86
        if not (radius - 38 <= dist <= radius + 42):
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return

        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self._is_dragging_dial = True
        self._timer_da.set_cursor_from_name("grabbing")
        if self.app.is_running:
            self.app.pause_timer()

        self._update_dial_from_coords(start_x, start_y)

    def _on_dial_drag_update(self, gesture, offset_x, offset_y):
        if not getattr(self, "_is_dragging_dial", False):
            return
        ok, start_x, start_y = gesture.get_start_point()
        if not ok:
            return
        self._update_dial_from_coords(start_x + offset_x, start_y + offset_y)

    def _on_dial_drag_end(self, _gesture, _offset_x, _offset_y):
        if getattr(self, "_is_dragging_dial", False):
            self._is_dragging_dial = False
            self._timer_da.set_cursor_from_name("grab" if self._dial_hover else "default")
            DataManager.save(self.app.data)
            self.refresh_timer()
            self.update_presets()

    def _update_dial_from_coords(self, x, y):
        w = self._timer_da.get_width()
        h = self._timer_da.get_height()
        xc, yc = w / 2, h / 2
        dx = x - xc
        dy = y - yc
        if abs(dx) < 1e-3 and abs(dy) < 1e-3:
            return

        angle = math.atan2(dy, dx) + math.pi / 2
        if angle < 0:
            angle += 2 * math.pi

        max_d = self.app.data["settings"].get("max_duration", 180)
        frac = angle / (2 * math.pi)
        target_mins = max(1, min(max_d, round(frac * max_d)))

        cur_mins = self.app.data["settings"]["work_duration"]
        if cur_mins <= max_d * 0.15 and target_mins >= max_d * 0.85:
            target_mins = 1
        elif cur_mins >= max_d * 0.85 and target_mins <= max_d * 0.15:
            target_mins = max_d

        self._set_custom_duration(target_mins, save=False)

    def _set_custom_duration(self, mins, save=True):
        self.app.pending_choice = False
        max_d = self.app.data["settings"].get("max_duration", 180)
        mins = max(1, min(max_d, mins))
        self._updating = True
        self.app.data["settings"]["work_duration"] = mins
        if hasattr(self, "_w_spin"):
            self._w_spin.set_value(mins)
        self._updating = False

        if self.app.state == "work" and not self.app.is_running:
            self.app.time_left = mins * 60

        if save:
            DataManager.save(self.app.data)

        self.refresh_timer()
        self.update_presets()

    def _on_custom_clicked(self, btn):
        pop = Gtk.Popover()
        pop.set_parent(btn)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
        lbl = Gtk.Label(label="Custom Focus Time (min)", css_classes=["caption", "dim-label"])
        box.append(lbl)
        max_d = self.app.data["settings"].get("max_duration", 180)
        spin = Gtk.SpinButton.new_with_range(1, max_d, 1)
        spin.set_value(self.app.data["settings"]["work_duration"])
        box.append(spin)
        set_btn = Gtk.Button(label="Apply", css_classes=["suggested-action"])

        def _apply(_):
            val = int(spin.get_value())
            self._set_custom_duration(val, save=True)
            pop.popdown()

        set_btn.connect("clicked", _apply)
        box.append(set_btn)
        pop.set_child(box)
        pop.popup()

    # ── event handlers ───────────────────────────────────────────────────
    def _on_play_pause(self, _b):
        if self.app.is_running:
            self.app.pause_timer()
        else:
            self.app.start_timer()

    def _on_action(self, _b):
        if self.app.state == "work":
            self.app.abandon_session()
        else:
            self.app.skip_break()

    def _on_preset(self, _b, mins):
        self._set_custom_duration(mins, save=True)

    def _on_add_task(self, _w):
        title = self._task_entry.get_text().strip()
        if not title:
            return
        pmap = {0: "high", 1: "medium", 2: "low"}
        task = {
            "id": str(uuid.uuid4()),
            "title": title,
            "estimated_pomos": int(self._pomo_spin.get_value()),
            "actual_pomos": 0,
            "completed": False,
            "priority": pmap.get(self._prio_dd.get_selected(), "medium"),
            "created": datetime.datetime.now().isoformat(),
        }
        self.app.data["tasks"].append(task)
        DataManager.save(self.app.data)
        self._task_entry.set_text("")
        self._pomo_spin.set_value(1)
        self._prio_dd.set_selected(1)
        self.refresh_tasks()

    def _on_clear(self, _b):
        self.app.data["tasks"] = [
            t for t in self.app.data["tasks"] if not t.get("completed")
        ]
        DataManager.save(self.app.data)
        self.refresh_tasks()

    def _on_task_check(self, ck, task):
        task["completed"] = ck.get_active()
        if task["completed"]:
            self.app.complete_task(task)
        DataManager.save(self.app.data)
        self.refresh_stats()

    def _on_task_activate(self, btn, task):
        if btn.get_active():
            self.app.active_task_id = task["id"]
        elif self.app.active_task_id == task["id"]:
            self.app.active_task_id = None
        self.refresh_tasks()
        self.refresh_timer()

    def _on_task_delete(self, _b, task):
        self.app.data["tasks"] = [
            t for t in self.app.data["tasks"] if t["id"] != task["id"]
        ]
        if self.app.active_task_id == task["id"]:
            self.app.active_task_id = None
        DataManager.save(self.app.data)
        self.refresh_tasks()

    def _on_task_move(self, _b, task, direction):
        tasks = self.app.data["tasks"]
        idx = next(
            (i for i, t in enumerate(tasks) if t["id"] == task["id"]), None
        )
        if idx is None:
            return
        ni = idx + direction
        if 0 <= ni < len(tasks):
            tasks[idx], tasks[ni] = tasks[ni], tasks[idx]
            DataManager.save(self.app.data)
            self.refresh_tasks()

    def _on_settings(self, *_a):
        if self._updating:
            return
        s = self.app.data["settings"]
        new_max = int(self._max_spin.get_value())
        s["max_duration"] = new_max
        self._w_spin.set_range(1, new_max)
        s["work_duration"] = min(new_max, int(self._w_spin.get_value()))
        s["short_break"] = int(self._sb_spin.get_value())
        s["long_break"] = int(self._lb_spin.get_value())
        s["pause_budget"] = int(self._pb_spin.get_value()) * 60
        s["sound"] = self._snd_sw.get_active()
        s["auto_start"] = self._auto_sw.get_active()
        s["reset_daily"] = self._rst_sw.get_active()
        s["auto_minimize"] = self._auto_min_sw.get_active()
        s["box_breathing_breaks"] = self._breath_sw.get_active()
        DataManager.save(self.app.data)
        if not self.app.is_running and not self.app.is_paused and self.app.state == "work":
            self.app.time_left = self.app.duration_for(self.app.state)
            self.refresh_timer()
        self.update_presets()
        self._timer_da.queue_draw()

    # ── refresh methods ──────────────────────────────────────────────────
    def refresh_timer(self):
        if self.app.pending_choice:
            self._time_lbl.set_text("Done!")
            self._active_lbl.set_text("Ready for next step")
            self._timer_da.queue_draw()
            return

        if self.app.box_breathing_active:
            self.refresh_breath_labels()
            self._timer_da.queue_draw()
            return

        mins, secs = divmod(self.app.time_left, 60)
        self._time_lbl.set_text(f"{mins:02d}:{secs:02d}")
        c = {"work": "timer-work", "short_break": "timer-short",
             "long_break": "timer-long"}[self.app.state]
        for cc in ("timer-work", "timer-short", "timer-long"):
            self._time_lbl.remove_css_class(cc)
        self._time_lbl.add_css_class(c)

        name = ""
        if self.app.active_task_id:
            for t in self.app.data["tasks"]:
                if t["id"] == self.app.active_task_id:
                    name = t["title"]
                    break
        self._active_lbl.set_text(name)
        self._timer_da.queue_draw()

    def refresh_breath_labels(self):
        st = BoxBreathingManager.get_state(self.app.breath_start_time)
        self._time_lbl.set_text(f"{st['sec_left']}")
        self._state_lbl.set_text(f"🫁 Box Breathing · {st['phase']} · Cycle {st['cycle']}")
        self._active_lbl.set_text(st["face"])

    def refresh_controls(self):
        if hasattr(self, "_choice_box"):
            if self.app.pending_choice:
                self._choice_box.set_visible(True)
                self._ctrls.set_visible(False)
                s_mins = self.app.data["settings"].get("short_break", 5)
                if self.app.session_count >= 4:
                    l_mins = self.app.data["settings"].get("long_break", 15)
                    self._main_break_btn.set_label(f"☕ {l_mins}m Break")
                    self._main_break_btn.set_tooltip_text(f"Start a {l_mins}-minute long break")
                else:
                    self._main_break_btn.set_label(f"☕ {s_mins}m Break")
                    self._main_break_btn.set_tooltip_text(f"Start a {s_mins}-minute short break")
            else:
                self._choice_box.set_visible(False)
                self._ctrls.set_visible(True)

        icon = ("media-playback-pause-symbolic" if self.app.is_running
                else "media-playback-start-symbolic")
        self._play_btn.set_icon_name(icon)

        if hasattr(self, "_breath_btn"):
            if self.app.box_breathing_active:
                self._breath_btn.set_label("⏹ Exit Breathing")
                self._breath_btn.add_css_class("active")
            else:
                self._breath_btn.set_label("🫁 Box Breathing")
                self._breath_btn.remove_css_class("active")

        if self.app.state == "work":
            self._act_btn.set_icon_name("process-stop-symbolic")
            self._act_btn.set_tooltip_text("Abandon session (−15 pts)")
            self._act_btn.remove_css_class("accent")
            self._act_btn.add_css_class("destructive-action")
            full = self.app.duration_for("work")
            started = (self.app.time_left < full
                       or self.app.is_running or self.app.is_paused)
            self._act_btn.set_sensitive(started)
        else:
            self._act_btn.set_icon_name("media-skip-forward-symbolic")
            self._act_btn.set_tooltip_text("Skip break")
            self._act_btn.remove_css_class("destructive-action")
            self._act_btn.set_sensitive(True)

        if self.app.is_paused:
            budget = self.app.data["settings"]["pause_budget"]
            left = max(0, budget - self.app.pause_used)
            m, s = divmod(left, 60)
            self._pause_lbl.set_text(f"⏸ Paused — {m}:{s:02d} remaining")
            self._pause_lbl.set_visible(True)
        else:
            self._pause_lbl.set_visible(False)

    def refresh_state_label(self):
        if self.app.pending_choice:
            self._state_lbl.set_text("🎉 Pomodoro Complete! Choose what's next:")
            return
        if self.app.box_breathing_active:
            st = BoxBreathingManager.get_state(self.app.breath_start_time)
            self._state_lbl.set_text(f"🫁 Box Breathing · {st['phase']} · Cycle {st['cycle']}")
            return
        labels = {
            "work": "Work",
            "short_break": "Short Break",
            "long_break": "Long Break",
        }
        txt = labels[self.app.state]
        if self.app.state == "work":
            txt += f" · Session {self.app.session_count}/4"
        self._state_lbl.set_text(txt)

    def refresh_tasks(self):
        while True:
            ch = self._task_list.get_first_child()
            if ch is None:
                break
            self._task_list.remove(ch)

        for task in self.app.data["tasks"]:
            row = Adw.ActionRow(
                title=task["title"],
                subtitle=(f'{task.get("actual_pomos", 0)}/'
                          f'{task.get("estimated_pomos", 1)} 🍅  ·  '
                          f'{task["priority"].capitalize()}'),
            )
            # priority dot
            dot = Gtk.Label(
                label="●", css_classes=[f'priority-{task["priority"]}'],
                valign=Gtk.Align.CENTER, margin_end=4,
            )
            row.add_prefix(dot)

            # checkbox
            ck = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            ck.set_active(task.get("completed", False))
            ck.connect("toggled", self._on_task_check, task)
            row.add_prefix(ck)

            # active toggle
            ab = Gtk.ToggleButton(
                icon_name="media-record-symbolic",
                css_classes=["flat", "circular"],
                valign=Gtk.Align.CENTER,
                tooltip_text="Work on this task",
            )
            ab.set_active(self.app.active_task_id == task["id"])
            ab.connect("toggled", self._on_task_activate, task)
            row.add_suffix(ab)

            # move
            up = Gtk.Button(
                icon_name="go-up-symbolic",
                css_classes=["flat", "circular"],
                valign=Gtk.Align.CENTER,
            )
            up.connect("clicked", self._on_task_move, task, -1)
            row.add_suffix(up)
            dn = Gtk.Button(
                icon_name="go-down-symbolic",
                css_classes=["flat", "circular"],
                valign=Gtk.Align.CENTER,
            )
            dn.connect("clicked", self._on_task_move, task, 1)
            row.add_suffix(dn)

            # delete
            db = Gtk.Button(
                icon_name="user-trash-symbolic",
                css_classes=["flat", "circular", "error"],
                valign=Gtk.Align.CENTER,
            )
            db.connect("clicked", self._on_task_delete, task)
            row.add_suffix(db)

            self._task_list.append(row)

    def refresh_stats(self):
        s = self.app.data["stats"]
        self._srows["daily_pomodoros"].set_text(str(s["daily_pomodoros"]))
        self._srows["daily_tasks_completed"].set_text(
            str(s["daily_tasks_completed"])
        )
        self._srows["daily_points"].set_text(str(s["daily_points"]))
        self._srows["current_streak"].set_text(str(s["current_streak"]))
        self._srows["total_points"].set_text(str(s["total_points"]))
        self._srows["total_pomodoros_all"].set_text(
            str(s["total_pomodoros"])
        )
        idx, title, into, needed = get_level(s["total_points"])
        self._lvl_lbl.set_text(f"Level {idx} — {title}")
        self._lvl_bar.set_fraction(min(into / needed, 1.0) if needed else 1)
        self._lvl_det.set_text(f"{into}/{needed} pts to next level")

        # achievements
        while True:
            ch = self._ach_flow.get_first_child()
            if ch is None:
                break
            self._ach_flow.remove(ch)
        unlocked = s.get("achievements", [])
        for a in ACHIEVEMENTS:
            ok = a["id"] in unlocked
            bx = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=2,
                halign=Gtk.Align.CENTER,
            )
            em = Gtk.Label(
                label=a["emoji"],
                css_classes=(["achievement-badge"]
                             + ([] if ok else ["achievement-locked"])),
                tooltip_text=a["desc"],
            )
            bx.append(em)
            nm = Gtk.Label(
                label=a["title"], css_classes=["caption"],
                max_width_chars=10, ellipsize=Pango.EllipsizeMode.END,
            )
            if not ok:
                nm.add_css_class("dim-label")
            bx.append(nm)
            self._ach_flow.append(bx)

    def update_presets(self):
        cur = self.app.data["settings"]["work_duration"]
        for m, b in self._preset_btns.items():
            b.remove_css_class("suggested-action")
            if m == cur:
                b.add_css_class("suggested-action")
        if hasattr(self, "_custom_btn"):
            if cur not in PRESETS:
                self._custom_btn.set_label(f"{cur}")
                self._custom_btn.add_css_class("suggested-action")
            else:
                self._custom_btn.set_label("Custom")
                self._custom_btn.remove_css_class("suggested-action")


# ═════════════════════════════════════════════════════════════════════════════
#  COMPACT WINDOW  — floating pill-shaped progress bar
# ═════════════════════════════════════════════════════════════════════════════
class CompactWindow(Gtk.Window):
    """
    A small draggable pill bar that shows the running timer.
    Drag anywhere to reposition (like Zoom's floating controls).
    Always-on-top is attempted via GNOME Shell D-Bus.
    """

    def __init__(self, app):
        super().__init__(title="Pomodoro Mini")
        self.app = app
        app.add_window(self)

        self.set_decorated(False)
        self.set_default_size(360, 48)
        self.set_resizable(False)
        self.set_icon_name("pomodoro")
        self.add_css_class("compact-win")

        self.connect("close-request", self._on_close)

        # WindowHandle → makes entire bar draggable
        handle = Gtk.WindowHandle()
        self.set_child(handle)

        overlay = Gtk.Overlay()
        handle.set_child(overlay)

        # Cairo canvas for pill background + progress fill
        self._canvas = Gtk.DrawingArea()
        self._canvas.set_draw_func(self._draw)
        overlay.set_child(self._canvas)

        # Stack allows smooth transitions between timer view and pomodoro end prompt view
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(150)

        # ── Timer box (normal mode) ──
        self._timer_box = Gtk.Box(
            spacing=6, margin_start=14, margin_end=8,
            halign=Gtk.Align.FILL, valign=Gtk.Align.CENTER,
        )

        pomo_icon = Gtk.Image.new_from_icon_name("pomodoro")
        pomo_icon.set_pixel_size(18)
        self._timer_box.append(pomo_icon)

        self._dot = Gtk.Label(label="●", css_classes=["compact-time"])
        self._timer_box.append(self._dot)

        self._time_lbl = Gtk.Label(
            label="25:00", css_classes=["compact-time"],
        )
        self._timer_box.append(self._time_lbl)

        self._timer_box.append(Gtk.Label(label="┊", css_classes=["compact-sep"]))

        self._task_lbl = Gtk.Label(
            css_classes=["compact-task"],
            hexpand=True, halign=Gtk.Align.START,
            ellipsize=Pango.EllipsizeMode.END, max_width_chars=20,
        )
        self._timer_box.append(self._task_lbl)

        self._play_btn = Gtk.Button(
            icon_name="media-playback-start-symbolic",
            css_classes=["flat", "circular", "compact-btn"],
        )
        self._play_btn.connect("clicked", self._on_play)
        self._timer_box.append(self._play_btn)

        exp = Gtk.Button(
            icon_name="view-fullscreen-symbolic",
            css_classes=["flat", "circular", "compact-btn"],
            tooltip_text="Expand",
        )
        exp.connect("clicked", lambda _: self.app.show_expanded())
        self._timer_box.append(exp)

        self._stack.add_named(self._timer_box, "timer")

        # ── Prompt box (when Pomodoro finishes) ──
        self._prompt_box = Gtk.Box(
            spacing=6, margin_start=8, margin_end=8,
            halign=Gtk.Align.FILL, valign=Gtk.Align.CENTER,
        )

        self._prompt_breath_btn = Gtk.Button(
            label="🫁 Breathe",
            css_classes=["compact-choice-btn", "choice-breath"],
            tooltip_text="Start a 4-4-4-4 Box Breathing relaxation",
            hexpand=True,
        )
        self._prompt_breath_btn.connect("clicked", lambda _: self.app.choose_breathing())
        self._prompt_box.append(self._prompt_breath_btn)

        self._prompt_break_btn = Gtk.Button(
            label="☕ 5m Break",
            css_classes=["compact-choice-btn", "choice-break"],
            tooltip_text="Start a 5-minute break timer",
            hexpand=True,
        )
        self._prompt_break_btn.connect("clicked", lambda _: self.app.choose_break())
        self._prompt_box.append(self._prompt_break_btn)

        self._prompt_next_btn = Gtk.Button(
            label="🍅 Next",
            css_classes=["compact-choice-btn", "choice-next"],
            tooltip_text="Start the next Pomodoro session",
            hexpand=True,
        )
        self._prompt_next_btn.connect("clicked", lambda _: self.app.choose_next_session())
        self._prompt_box.append(self._prompt_next_btn)

        exp2 = Gtk.Button(
            icon_name="view-fullscreen-symbolic",
            css_classes=["flat", "circular", "compact-btn"],
            tooltip_text="Expand",
        )
        exp2.connect("clicked", lambda _: self.app.show_expanded())
        self._prompt_box.append(exp2)

        self._stack.add_named(self._prompt_box, "prompt")

        overlay.add_overlay(self._stack)

    # ── events ───────────────────────────────────────────────────────────
    def _on_close(self, _w):
        self.app.show_expanded()
        return True  # prevent destruction

    def _on_play(self, _b):
        if self.app.box_breathing_active:
            self.app.toggle_box_breathing()
            return
        if self.app.is_running:
            self.app.pause_timer()
        else:
            self.app.start_timer()

    # ── refresh ──────────────────────────────────────────────────────────
    def refresh(self):
        if self.app.pending_choice:
            s_mins = self.app.data["settings"].get("short_break", 5)
            if self.app.session_count >= 4:
                l_mins = self.app.data["settings"].get("long_break", 15)
                self._prompt_break_btn.set_label(f"☕ {l_mins}m Break")
                self._prompt_break_btn.set_tooltip_text(f"Start a {l_mins}-minute long break")
            else:
                self._prompt_break_btn.set_label(f"☕ {s_mins}m Break")
                self._prompt_break_btn.set_tooltip_text(f"Start a {s_mins}-minute short break")
            self._stack.set_visible_child_name("prompt")
            self._canvas.queue_draw()
            return

        self._stack.set_visible_child_name("timer")

        if self.app.box_breathing_active:
            self.refresh_breath_labels()
            self._play_btn.set_icon_name("media-playback-stop-symbolic")
            self._play_btn.set_tooltip_text("Exit Box Breathing")
            self._canvas.queue_draw()
            return

        self._play_btn.set_tooltip_text("Play / Pause")
        mins, secs = divmod(self.app.time_left, 60)
        self._time_lbl.set_text(f"{mins:02d}:{secs:02d}")

        # dot colour
        cmap = {
            "work": "timer-work",
            "short_break": "timer-short",
            "long_break": "timer-long",
        }
        for c in cmap.values():
            self._dot.remove_css_class(c)
        self._dot.add_css_class(cmap.get(self.app.state, "timer-work"))

        # pause vs task display
        if self.app.is_paused:
            self._dot.set_text("⏸")
            budget = self.app.data["settings"]["pause_budget"]
            left = max(0, budget - self.app.pause_used)
            m, s = divmod(left, 60)
            self._task_lbl.set_text(f"Paused {m}:{s:02d}")
        else:
            self._dot.set_text("●")
            name = ""
            if self.app.active_task_id:
                for t in self.app.data["tasks"]:
                    if t["id"] == self.app.active_task_id:
                        name = t["title"]
                        break
            self._task_lbl.set_text(name)

        icon = ("media-playback-pause-symbolic" if self.app.is_running
                else "media-playback-start-symbolic")
        self._play_btn.set_icon_name(icon)

        self._canvas.queue_draw()

    def refresh_breath_labels(self):
        st = BoxBreathingManager.get_state(self.app.breath_start_time)
        self._dot.set_text(st["face"])
        self._time_lbl.set_text(f"{st['phase']} {st['sec_left']}s")
        self._task_lbl.set_text(f"🫁 {st['instruction']}")

    # ── Cairo drawing ────────────────────────────────────────────────────
    def _draw(self, _a, cr, w, h):
        m = 2
        pw, ph = w - 2 * m, h - 2 * m
        r = ph / 2

        # dark pill background
        _pill(cr, m, m, pw, ph, r)
        cr.set_source_rgba(0.07, 0.07, 0.11, 0.93)
        cr.fill()

        # Check if Box Breathing is active vs normal timer
        is_breathing = self.app.box_breathing_active
        r_c, g_c, b_c = (0.5, 0.5, 0.5)
        if self.app.pending_choice:
            fill_w = 0.0
            is_anim = False
        elif is_breathing:
            st = BoxBreathingManager.get_state(self.app.breath_start_time)
            r_c, g_c, b_c = st["color"]
            if st["phase_idx"] == 0:    # Inhale: ocean waves swelling forward
                fill_w = max(16.0, pw * st["scale"])
            elif st["phase_idx"] == 1:  # Hold full: deep full water with high tide
                fill_w = pw
            elif st["phase_idx"] == 2:  # Exhale: waves gently receding
                fill_w = max(16.0, pw * st["scale"])
            else:                       # Hold empty: calm resting lagoon
                fill_w = max(16.0, pw * 0.16)
            is_anim = True
        else:
            full = self.app.duration_for(self.app.state)
            elapsed = full - self.app.time_left
            progress = elapsed / full if full > 0 else 0
            r_c, g_c, b_c = STATE_COLORS.get(self.app.state, (0.5, 0.5, 0.5))
            fill_w = pw * progress
            is_anim = self.app.is_running

        if is_anim:
            self._last_t = time.time()
        t = getattr(self, "_last_t", 0.0)

        # Water fill with gentle subtle shake
        if fill_w > 2.0:
            cr.save()
            _pill(cr, m, m, pw, ph, r)
            cr.clip()

            steps = 16
            cr.move_to(m, m)
            cr.line_to(m, m + ph)
            for s in range(steps + 1):
                y = m + ph - (s / steps) * ph
                k = (y - m) / ph
                # Subtle gentle water shake
                shake = 1.2 * math.sin(k * 2.0 * math.pi + t * 2.4) if is_anim else 0.0
                wx = min(m + pw, max(m, m + fill_w + shake))
                cr.line_to(wx, y)
            cr.close_path()

            # Clean translucent water fill
            cr.set_source_rgba(r_c, g_c, b_c, 0.40)
            cr.fill()

            # Soft subtle water meniscus highlight on the leading edge
            if is_anim:
                cr.set_line_width(1.0)
                cr.set_source_rgba(min(1.0, r_c + 0.35), min(1.0, g_c + 0.35), min(1.0, b_c + 0.35), 0.35)
                for s in range(steps + 1):
                    y = m + ph - (s / steps) * ph
                    k = (y - m) / ph
                    shake = 1.2 * math.sin(k * 2.0 * math.pi + t * 2.4)
                    wx = min(m + pw, max(m, m + fill_w + shake))
                    if s == 0:
                        cr.move_to(wx, y)
                    else:
                        cr.line_to(wx, y)
                cr.stroke()

            cr.restore()

        # Subtle border
        _pill(cr, m + 0.5, m + 0.5, pw - 1, ph - 1, r - 0.5)
        if self.app.pending_choice:
            cr.set_source_rgba(0.95, 0.65, 0.20, 0.50)
            cr.set_line_width(1.5)
        elif is_breathing:
            cr.set_source_rgba(r_c, g_c, b_c, 0.45 + 0.25 * st["scale"])
            cr.set_line_width(1.5)
        else:
            cr.set_source_rgba(1, 1, 1, 0.08)
            cr.set_line_width(1.0)
        cr.stroke()

    # ── always-on-top & sticky across workspaces ────────────────────────
    def try_pin_above(self):
        """Pin floating mini bar to all workspaces and keep above all windows."""
        X11WindowManager.pin_to_all_workspaces_and_top(self)
        return False


# ═════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═════════════════════════════════════════════════════════════════════════════
def main():
    app = PomodoroApp()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
