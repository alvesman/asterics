#!/bin/bash
# AsTeRICS face-tracking mouse for GNOME/Wayland (Ubuntu 26.04).
# Starts: uinput daemon (ydotoold) -> OSC-to-uinput bridge -> ARE with the XFaceTrackerMouse_uinput model.
# Stop everything by closing the ARE window.
#   start-facemouse.sh          full control panel (Right/Double/Drag/On-Off, speed slider, camera preview)
#                               in a normal window with a minimise button, not always on top
#   start-facemouse.sh --quiet  no camera preview / buttons; window minimised if xdotool is installed
set -u
MODEL=XFaceTrackerMouse_uinput.acs; [ "${1:-}" = "--quiet" ] && MODEL=XFaceTrackerMouse_uinput_quiet.acs
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG=${XDG_STATE_HOME:-$HOME/.local/state}/asterics-facemouse; mkdir -p "$LOG"

# 1. uinput daemon: prefer the per-user service (needs membership of the 'input' group),
#    otherwise fall back to an already running system-wide daemon socket.
if id -nG | grep -qw input; then
    systemctl --user start ydotool.service 2>/dev/null
    SOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/.ydotool_socket"
    for _ in 1 2 3 4 5 6 7 8 9 10; do [ -S "$SOCK" ] && break; sleep 0.3; done
else
    SOCK=/tmp/.ydotool_socket
fi
if [ ! -S "$SOCK" ]; then
    MSG="No uinput daemon socket. Add yourself to the 'input' group (sudo usermod -aG input \$USER), then log out and in."
    echo "$MSG" >&2; command -v zenity >/dev/null && zenity --error --text="$MSG" 2>/dev/null; exit 1
fi
export YDOTOOL_SOCKET="$SOCK"

# 2. bridge (one instance only)
pkill -f "asterics_uinput_bridge.py" 2>/dev/null
python3 -I "$HERE/asterics_uinput_bridge.py" >"$LOG/bridge.log" 2>&1 &
BRIDGE=$!
trap 'kill $BRIDGE 2>/dev/null' EXIT

# 3. quiet mode: minimise the ARE window once it appears (needs xdotool; harmless if missing)
if [ "$MODEL" = XFaceTrackerMouse_uinput_quiet.acs ] && command -v xdotool >/dev/null; then
    ( for _ in $(seq 60); do
          W=$(xdotool search --name "AsTeRICS ARE" 2>/dev/null | head -1)
          [ -n "$W" ] && { sleep 2; xdotool windowminimize "$W" 2>/dev/null; break; }
          sleep 1
      done ) &
fi

# 4. ARE with the uinput model; blocks until the ARE window is closed
/opt/asterics-are/app/start.sh "$MODEL" >"$LOG/are.log" 2>&1
