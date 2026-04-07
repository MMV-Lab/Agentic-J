#!/bin/bash
set -e

# ── Clean up stale X11 lock files from previous runs ─────────────────────────
# This prevents "Server is already active for display 1" errors on restart
rm -f /tmp/.X1-lock
rm -f /tmp/.X11-unix/X1

# ── Apply pending Fiji updates ───────────────────────────────────────────────
# Fiji stages updates in /opt/Fiji.app/update/ - move them to their destinations
FIJI_HOME=/opt/Fiji.app
if [ -d "$FIJI_HOME/update" ] && [ "$(ls -A $FIJI_HOME/update 2>/dev/null)" ]; then
    echo "[entrypoint] Applying pending Fiji updates..."
    # Copy plugins
    if [ -d "$FIJI_HOME/update/plugins" ]; then
        cp -rv "$FIJI_HOME/update/plugins/"* "$FIJI_HOME/plugins/" 2>/dev/null || true
    fi
    # Copy jars
    if [ -d "$FIJI_HOME/update/jars" ]; then
        cp -rv "$FIJI_HOME/update/jars/"* "$FIJI_HOME/jars/" 2>/dev/null || true
    fi
    # Copy macros
    if [ -d "$FIJI_HOME/update/macros" ]; then
        cp -rv "$FIJI_HOME/update/macros/"* "$FIJI_HOME/macros/" 2>/dev/null || true
    fi
    # Copy scripts
    if [ -d "$FIJI_HOME/update/scripts" ]; then
        cp -rv "$FIJI_HOME/update/scripts/"* "$FIJI_HOME/scripts/" 2>/dev/null || true
    fi
    # Clean up update directory after applying
    rm -rf "$FIJI_HOME/update/"*
    echo "[entrypoint] Updates applied successfully"
fi

# ── Prepare runtime directories (tmpfs mounts start empty) ───────────────────
mkdir -p /tmp/.X11-unix
mkdir -p /home/imagentj/.fluxbox

# ── Start virtual display ────────────────────────────────────────────────────
echo "[entrypoint] Starting Xvfb on display :1 (1280x800x24)..."
Xvfb :1 -screen 0 1280x800x24 -ac +extension GLX +render -noreset &

export DISPLAY=:1

# echo "[entrypoint] Enabling keyboard repeat..."
# xset r on
# xset r rate 300 50

# Wait for X11 socket to be ready
echo "[entrypoint] Waiting for Xvfb to be ready..."
for i in $(seq 1 60); do
    if [ -e /tmp/.X11-unix/X1 ]; then
        echo "[entrypoint] Xvfb socket found after $i attempts"
        sleep 2  # Extra delay after socket appears
        break
    fi
    if [ $i -eq 60 ]; then
        echo "[entrypoint] WARNING: Xvfb socket not found after 30s"
        ls -la /tmp/.X11-unix/ 2>/dev/null || echo "Directory doesn't exist"
    fi
    sleep 0.5
done

# ── Start window manager ─────────────────────────────────────────────────────
echo "[entrypoint] Starting fluxbox window manager..."
fluxbox &
sleep 1

# ── Start VNC server ─────────────────────────────────────────────────────────
echo "[entrypoint] Starting x11vnc on display :1..."
if [ -n "$VNC_PASSWORD" ]; then
    # Create password file if VNC_PASSWORD is set
    mkdir -p /home/imagentj/.vnc
    x11vnc -storepasswd "$VNC_PASSWORD" /home/imagentj/.vnc/passwd 2>/dev/null
    x11vnc -display :1 -forever -rfbauth /home/imagentj/.vnc/passwd -shared -rfbport 5900 -quiet &
    echo "[entrypoint] VNC started with password authentication"
else
    x11vnc -display :1 -forever -nopw -shared -rfbport 5900 -quiet &
    echo "[entrypoint] WARNING: VNC started WITHOUT password (set VNC_PASSWORD env var for security)"
fi
sleep 1

# ── Start noVNC websocket proxy ──────────────────────────────────────────────
echo "[entrypoint] Starting noVNC on port 6080..."
websockify --web /usr/share/novnc 6080 localhost:5900 &
sleep 1

echo "[entrypoint] noVNC is listening on http://localhost:6080"

# ── Validate API key ─────────────────────────────────────────────────────────
if [ -z "$OPENAI_API_KEY" ]; then
    echo "[entrypoint] WARNING: OPENAI_API_KEY is not set. The agent will not work without it."
fi

# ── Launch the application ───────────────────────────────────────────────────
# PATH is already set in Dockerfile to include the conda env; no need to activate
echo "[entrypoint] Launching: $@"
exec "$@"