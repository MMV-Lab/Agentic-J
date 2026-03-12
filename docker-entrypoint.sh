#!/bin/bash
set -e

# ── Clean up stale X11 lock files from previous runs ─────────────────────────
# This prevents "Server is already active for display 1" errors on restart
rm -f /tmp/.X1-lock
rm -f /tmp/.X11-unix/X1

# ── Fix CSBDeep/StarDist protobuf JAR conflict ───────────────────────────────
# CSBDeep's TensorFlow 1.x bindings require protobuf-java-3.6.x.
# The makeExtensionsImmutable() NoSuchMethodError is caused by a newer protobuf
# JAR shadowing the version TF was compiled against. Replace it at startup since
# fiji_jars is a named volume that survives image rebuilds.
FIJI_JARS=/opt/Fiji.app/jars
REQUIRED_PROTOBUF="protobuf-java-3.6.1.jar"
if [ ! -f "$FIJI_JARS/$REQUIRED_PROTOBUF" ]; then
    echo "[entrypoint] Fixing protobuf JAR for CSBDeep/StarDist compatibility..."
    # Remove any protobuf JAR that would conflict (including the util sibling,
    # which targets 4.x and would cause Updater "locally modified" warnings)
    rm -f "$FIJI_JARS"/protobuf-java-*.jar
    rm -f "$FIJI_JARS"/protobuf-java-util-*.jar
    wget -q "https://repo1.maven.org/maven2/com/google/protobuf/protobuf-java/3.6.1/protobuf-java-3.6.1.jar" \
         -O "$FIJI_JARS/$REQUIRED_PROTOBUF" \
    && echo "[entrypoint] protobuf-java-3.6.1.jar installed" \
    || echo "[entrypoint] WARNING: failed to download protobuf JAR — StarDist may not work"
fi

# ── Remove duplicate JAR versions from fiji_jars ─────────────────────────────
# Fiji's updater throws "multiple existing versions" critical errors when both
# old and new versions of the same JAR coexist (e.g. imglib2-7.0.0.jar AND
# imglib2-7.1.4.jar). This happens because the fiji_jars named volume persists
# across rebuilds while agent-installed plugins pull in newer dependency versions.
echo "[entrypoint] Deduplicating JAR versions in fiji_jars..."
python3 -c "
import re
from pathlib import Path
from collections import defaultdict

jars_dir = Path('/opt/Fiji.app/jars')
groups = defaultdict(list)

for jar in jars_dir.glob('*.jar'):
    m = re.match(r'^(.+?)-(\d.*)\.jar$', jar.name)
    if m:
        groups[m.group(1)].append(jar)

removed = 0
for base, jars in groups.items():
    if len(jars) > 1:
        jars_sorted = sorted(jars, key=lambda j: j.name)
        for old in jars_sorted[:-1]:
            print(f'[entrypoint] Removing older duplicate: {old.name}  (keeping {jars_sorted[-1].name})')
            old.unlink()
            removed += 1

print(f'[entrypoint] Removed {removed} duplicate JAR(s)') if removed else print('[entrypoint] No duplicate JARs found')
" 2>&1 || echo "[entrypoint] WARNING: JAR deduplication skipped"

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
    # Copy native libraries (e.g. TensorFlow .so files for CSBDeep/StarDist)
    # if [ -d "$FIJI_HOME/update/lib" ]; then
    #     cp -rv "$FIJI_HOME/update/lib/"* "$FIJI_HOME/lib/" 2>/dev/null || true
    # fi
    # Clean up update directory after applying
    rm -rf "$FIJI_HOME/update/"*
    echo "[entrypoint] Updates applied successfully"
fi

# ── Prepare runtime directories (tmpfs mounts start empty) ───────────────────
mkdir -p /tmp/.X11-unix
mkdir -p /home/imagentj/.fluxbox

# Single workspace so the user can't accidentally switch away from Fiji
cat > /home/imagentj/.fluxbox/init << 'EOF'
session.screen0.workspaces: 1
session.screen0.workspaceNames: Fiji
EOF

# ── Start virtual display ────────────────────────────────────────────────────
echo "[entrypoint] Starting Xvfb on display :1..."
Xvfb :1 -screen 0 1840x1020x24 -ac +extension GLX +render -noreset &

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
