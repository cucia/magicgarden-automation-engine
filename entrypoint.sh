#!/bin/bash
set -e

echo "=============================="
echo "[ENTRYPOINT] Container started"
echo "[ENTRYPOINT] BROWSER_PROFILE_DIR=${BROWSER_PROFILE_DIR}"
echo "=============================="

# Default values (safety)
DISPLAY_NUM=${DISPLAY_NUM:-99}
BROWSER_PROFILE_DIR=${BROWSER_PROFILE_DIR:-/app/browser-profile}

# Ensure profile dir exists
mkdir -p "$BROWSER_PROFILE_DIR"

# Clean up stale processes and locks
echo "[CLEANUP] Killing stale X11/VNC processes..."
pkill -f Xvfb || true
pkill -f x11vnc || true
sleep 1
rm -f /tmp/.X${DISPLAY_NUM}-lock

export DISPLAY=:$DISPLAY_NUM
echo "[Xvfb] Starting virtual display on $DISPLAY"
Xvfb $DISPLAY -screen 0 1920x1080x24 &
sleep 2

echo "[MODE] Headed (GUI) mode ENABLED - accessible on port 5900"
echo "[x11vnc] Starting VNC server"
x11vnc -display $DISPLAY -forever -nopw -shared -rfbport 5900 &

echo "[APP] Cleaning Chromium SingletonLock"
rm -f "$BROWSER_PROFILE_DIR/SingletonLock"
rm -f "$BROWSER_PROFILE_DIR/.user-data-dir/SingletonLock"

echo "[APP] Launching automation engine"
exec python main.py
