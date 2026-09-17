# Floating Pomodoro Timer for Linux (GNOME / Wayland / X11)

A feature-rich, modern floating Pomodoro timer built with **Python 3**, **GTK4**, **Libadwaita**, and **Cairo**.

---

## ✨ Features

### 1. 🪟 Floating Mini Pill Window
- **Always-on-top & Multi-workspace Sticky**: Uses EWMH X11/Xwayland hinting (`_NET_WM_DESKTOP = 0xFFFFFFFF`, `_NET_WM_STATE_STICKY`, `_NET_WM_STATE_ABOVE`) to follow you across all virtual workspaces.
- **Draggable & Compact**: Small 320x48 px pill bar that can be dragged and repositioned anywhere on screen.
- **Auto-Minimize on Window Switch**: Automatically collapses from the expanded window to the floating mini bar when switching active windows.

### 2. ⏱ Interactive Draggable Timer Ring & Custom Time
- **Chronometer Bezel & Dial**: Circular progress ring with outer bezel tick marks every 15 minutes and major marks (30, 60, 90, 120, 150, 180 min).
- **Interactive Draggable Knob**: Grab and drag the handle around the clock to intuitively change the session duration.
- **Custom Time up to 180+ min**: Set any custom duration via the draggable ring, preset buttons (`[25]`, `[45]`, `[60]`), or the `[Custom]` popover.
- **Configurable Max Duration**: In **Settings**, adjust the maximum dial limit from 30 up to 360 minutes (defaults to 180 min).

### 3. 🌊 Gentle Water Progress Bar
- **Liquid Water Ripple**: Subtle, calming liquid shake along the leading edge of the progress bar to show fluid movement.
- **Idle Freeze (0% CPU)**: The 30 FPS Cairo animation loop automatically shuts down when paused or idle to save battery and CPU.

### 4. 🫁 4-4-4-4 Box Breathing Relaxation
- **Guided Meditation**: 4s Inhale → 4s Hold → 4s Exhale → 4s Hold with animated cues and soothing facial expressions:
  - Inhale: `( ˘▽˘ )`
  - Hold: `( ˘◡˘ )`
  - Exhale: `( ˘o˘ )`
  - Rest: `( ◡‿◡ )`
- Available in both expanded and floating mini modes.

### 5. 📋 Task Management & Rewards
- **Task List**: Add, prioritize (High/Medium/Low), reorder, track, and complete daily tasks.
- **Gamified Scoring**: Points for completed pomodoros (+10) and tasks (+25), streak multipliers, and achievement badges.
- **Pause Budget**: 2-minute editable pause budget per session with deductions for abandoning sessions.

---

## 📦 System Requirements & Dependencies

- **Operating System**: Linux (Ubuntu 22.04+, Fedora 36+, Debian 12+, Arch Linux, Manjaro, Linux Mint, etc.)
- **Desktop Environment**: GNOME Shell 40+ recommended (or any desktop supporting GTK4)
- **Display Server**: Wayland (via Xwayland) or native X11
- **Python**: Python 3.10 or newer

---

## 🛠️ Installation

### 1. Install Dependencies by Distribution

#### **Ubuntu / Debian / Linux Mint**
```bash
sudo apt update
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 libnotify-bin pulseaudio-utils x11-utils
```

#### **Fedora / RHEL**
```bash
sudo dnf install python3-gobject python3-cairo gtk4 libadwaita libnotify pulseaudio-utils xorg-x11-utils
```

#### **Arch Linux / Manjaro**
```bash
sudo pacman -S python-gobject python-cairo gtk4 libadwaita libnotify pulseaudio-utils xorg-xprop
```

---

## 🚀 How to Run on a New System

### Option A: Run Directly (Portable)
Navigate to the project folder and execute the launcher script:
```bash
cd pomodoro-timer
chmod +x run.sh
./run.sh
```
Or run directly with Python:
```bash
python3 pomodoro.py
```

---

### Option B: Install into System (Application Menu & Shortcut)

To make the app appear in your GNOME / system application launcher menu with its tomato icon:

1. **Copy application files to `~/.local/share/pomodoro/`**:
   ```bash
   mkdir -p ~/.local/share/pomodoro
   cp -r * ~/.local/share/pomodoro/
   chmod +x ~/.local/share/pomodoro/run.sh ~/.local/share/pomodoro/pomodoro.py
   ```

2. **Install Desktop Entry**:
   ```bash
   mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
   cp pomodoro.desktop ~/.local/share/applications/
   cp pomodoro.svg ~/.local/share/icons/hicolor/scalable/apps/
   ```

3. **Update Icon & Desktop Database**:
   ```bash
   gtk-update-icon-cache ~/.local/share/icons/hicolor/ 2>/dev/null || true
   update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
   ```

Now you can launch **Pomodoro Timer** directly from your application launcher or search `Pomodoro` in your desktop menu!

---

## 📁 Project Structure

```
pomodoro-timer/
├── pomodoro.py       # Main GTK4 / Libadwaita application source code
├── pomodoro.svg      # Custom tomato application icon
├── run.sh            # Launcher script (configures GDK_BACKEND=x11)
├── pomodoro.desktop  # Desktop launcher entry
└── README.md         # Documentation and setup guide
```
