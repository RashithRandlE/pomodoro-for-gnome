#!/bin/bash
# Pomodoro Timer Launcher
# Sets X11/Xwayland backend so Mutter/GNOME Shell supports sticky windows across all workspaces and always-on-top

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "$DISPLAY" ] && [ -z "$GDK_BACKEND" ]; then
    export GDK_BACKEND=x11
fi

exec python3 "$DIR/pomodoro.py" "$@"
