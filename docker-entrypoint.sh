#!/bin/bash
set -e

# ── Seed Fiji named volumes on first run ─────────────────────────────────────
# Named volumes mount as empty directories, shadowing the image's baked-in
# plugins/jars. Seed from .seed dirs on first start (marker file = already done).
FIJI_HOME=/opt/Fiji.app

# Seed helper: copies seed → dest, skipping files that already exist.
# Uses Python so permission errors on individual files are caught and reported
# rather than aborting the whole entrypoint (which 'cp -a' + set -e would do).
#
# NOTE: The marker file is intentionally NOT used to skip the copy. The Python
# copy is idempotent (skips files that already exist in the destination), so it
# is safe to run on every container start. This is critical: without this, new
# plugin JARs added to the image (e.g. StarDist, CSBDeep) are never propagated
# to the named volumes when those volumes were created by an older image build.
_seed_volume() {
    local label="$1" src="$2" dst="$3" marker="$4"
    echo "[entrypoint] Seeding $label from image (skips existing files)..."
    python3 - "$src" "$dst" <<'PYEOF'
import sys, shutil
from pathlib import Path
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
ok = skip = fail = 0
for f in src.rglob('*'):
    if not f.is_file():
        continue
    target = dst / f.relative_to(src)
    if target.exists():
        skip += 1
        continue
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(f), str(target))
        ok += 1
    except (PermissionError, OSError) as e:
        fail += 1
        print(f'[entrypoint] WARNING: cannot seed {target.name}: {e}', flush=True)
print(f'[entrypoint] seeded: {ok} copied, {skip} already present, {fail} permission-denied', flush=True)
PYEOF
    touch "$marker" 2>/dev/null || true
    echo "[entrypoint] $label seeding complete"
}

_seed_volume "fiji_jars"    "$FIJI_HOME/jars.seed"    "$FIJI_HOME/jars"    "$FIJI_HOME/jars/.seeded"
_seed_volume "fiji_plugins" "$FIJI_HOME/plugins.seed" "$FIJI_HOME/plugins" "$FIJI_HOME/plugins/.seeded"
_seed_volume "imagentj_home" "/home/imagentj.seed" "/home/imagentj" "/home/imagentj/.seeded"

# ── Enforce TrackMate-StarDist ClassCastException patch ───────────────────────
# _seed_volume skips files that already exist, so a stale unpatched JAR in the
# fiji_jars volume survives image rebuilds. Compare checksums and overwrite if needed.
_STARDIST_JAR="$FIJI_HOME/jars/TrackMate-StarDist-2.0.0.jar"
_PATCHED_JAR="/opt/fiji-patches/TrackMate-StarDist-2.0.0.jar.patched"
if [ -f "$_PATCHED_JAR" ] && [ -f "$_STARDIST_JAR" ]; then
    if ! cmp -s "$_PATCHED_JAR" "$_STARDIST_JAR"; then
        echo "[entrypoint] Applying TrackMate-StarDist ClassCastException patch to volume JAR..."
        cp "$_PATCHED_JAR" "$_STARDIST_JAR"
        echo "[entrypoint] TrackMate-StarDist patch applied."
    fi
fi

# ── Enforce CSBDeep linux/arm64 TensorFlow Java patch ───────────────────────
# Existing fiji_jars volumes can keep the old upstream JAR, whose TensorFlow
# Java 1.x JNI dependency has no linux/aarch64 native library. Keep the patched
# single-JAR TensorFlow Java backend in the volume even after rebuilds.
case "$(uname -m)" in
    aarch64|arm64)
        _CSBDEEP_JAR="$FIJI_HOME/jars/csbdeep-0.6.0.jar"
        _CSBDEEP_PATCHED_JAR="/opt/fiji-patches/csbdeep-0.6.0-tfjava-linux-arm64.jar"
        if [ -f "$_CSBDEEP_PATCHED_JAR" ] && [ -f "$_CSBDEEP_JAR" ]; then
            if ! cmp -s "$_CSBDEEP_PATCHED_JAR" "$_CSBDEEP_JAR"; then
                echo "[entrypoint] Applying CSBDeep linux/arm64 TensorFlow Java patch to volume JAR..."
                cp "$_CSBDEEP_PATCHED_JAR" "$_CSBDEEP_JAR"
                echo "[entrypoint] CSBDeep TensorFlow Java arm64 patch applied."
            fi
        fi
        ;;
    *)
        echo "[entrypoint] Skipping CSBDeep linux/arm64 TensorFlow Java patch on $(uname -m)."
        ;;
esac

# ── Clean up stale X11 lock files from previous runs ─────────────────────────
# This prevents "Server is already active for display 1" errors on restart
rm -f /tmp/.X1-lock
rm -f /tmp/.X11-unix/X1

# ── Clean up stale Qdrant lock file ──────────────────────────────────────────
# Qdrant local mode creates /app/qdrant_data/.lock on startup. If the container
# previously crashed, or the file was created by a different user (e.g. rstudio-server),
# the lock becomes stale and blocks RAG initialization with [Errno 13] Permission denied.
# The parent directory is world-writable, so rm works regardless of the lock's owner.
rm -f /app/qdrant_data/.lock && echo "[entrypoint] Removed stale Qdrant lock" || true

# ── Ensure Nashorn JavaScript engine JAR is present ──────────────────────────
# Java 15+ removed the built-in Nashorn engine. Rhino (also installed) covers
# generic JSR-223 JS, but Fiji macros that request the engine by the name
# "nashorn" specifically will not find it without the standalone nashorn-core JAR.
# This check ensures the JAR is in the fiji_jars volume even on pre-existing
# volumes that predate its addition to the image.
NASHORN_JAR="$FIJI_HOME/jars/nashorn-core-15.4.jar"
if [ ! -f "$NASHORN_JAR" ]; then
    echo "[entrypoint] Downloading nashorn-core-15.4.jar (JavaScript engine)..."
    wget -q -O "$NASHORN_JAR" \
        "https://repo1.maven.org/maven2/org/openjdk/nashorn/nashorn-core/15.4/nashorn-core-15.4.jar" \
    && echo "[entrypoint] nashorn-core-15.4.jar installed" \
    || { echo "[entrypoint] WARNING: failed to download nashorn-core JAR — .js macros may not work"; rm -f "$NASHORN_JAR"; }
fi

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


# ── JAR deduplication helper (called before and after applying updates) ───────
# Removes older versions of any JAR when multiple versions of the same lib exist.
# Searches jars/ and all subdirectories (e.g. jars/bio-formats/).
deduplicate_jars() {
    local label="${1:-jars}"
    echo "[entrypoint] Deduplicating JAR versions ($label)..."
    python3 -c "
import re, sys
from pathlib import Path
from collections import defaultdict

jars_dir = Path('/opt/Fiji.app/jars')
groups = defaultdict(list)

for jar in jars_dir.rglob('*.jar'):
    m = re.match(r'^(.+?)-(\d.*)\.jar\$', jar.name)
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
}

# ── Remove duplicate JAR versions from fiji_jars (pre-update pass) ───────────
# Clean up any stale duplicates already in the named volume before applying updates.
deduplicate_jars "pre-update"

# ── Protect pyimagej-critical JARs from incompatible updates ─────────────────
# pyimagej 1.7.0 requires net.imagej.updater.UploaderService. Newer builds from
# the Fiji update sites removed this class. Drop the staged updates for these
# JARs so the base Fiji versions (which still have the class) are preserved.
FIJI_HOME=/opt/Fiji.app
# Log everything staged so we can see exactly what the update sites downloaded
echo "[entrypoint] Staged update jars/:"
ls "$FIJI_HOME/update/jars/" 2>/dev/null | sed 's/^/  /' || echo "  (empty or missing)"
echo "[entrypoint] Staged update plugins/:"
ls "$FIJI_HOME/update/plugins/" 2>/dev/null | sed 's/^/  /' || echo "  (empty or missing)"

# Drop updates for JARs that are incompatible with pyimagej 1.7.0.
# Bio-Formats 8.x and newer SCIFIO/OME JARs break pyimagej 1.7.0.
# JARs may live in subdirectories (e.g. update/jars/bio-formats/), so use find.

# Remove the entire bio-formats subdirectory if present
if [ -d "$FIJI_HOME/update/jars/bio-formats" ]; then
    echo "[entrypoint] Removing update/jars/bio-formats/ (incompatible with pyimagej 1.7.0)"
    rm -rf "$FIJI_HOME/update/jars/bio-formats"
fi

# Remove individual protected JARs anywhere under update/ by name pattern
find "$FIJI_HOME/update" -type f -name "*.jar" | while read -r f; do
    base=$(basename "$f")
    case "$base" in
        imagej-updater-*|imagej-legacy-*|imagej-common-* \
        |formats-api-*|formats-bsd-*|formats-common-*|formats-gpl-* \
        |bioformats_package-*|bioformats-* \
        |scifio-*|scifio-ome-xml-* \
        |ome-common-*|ome-xml-*|ome-codecs-*|specification-* \
        |jai_imageio_core-*|turbojpeg-*|metakit-*)
            echo "[entrypoint] Skipping $base (pyimagej 1.7.0 compatibility)"
            rm "$f"
            ;;
        TrackMate-StarDist-[01].*)
            echo "[entrypoint] Skipping $base (pre-2.0 — incompatible API for TrackMate 8.x)"
            rm "$f"
            ;;
    esac
done

# ── Remove stale TrackMate-StarDist 1.2.0 from named volume ──────────────────
# 1.2.0 has AbstractMethodError with TrackMate 8.x (missing 4-arg getDetector).
# The image now ships patched 2.0.0; remove any 1.x lingering in the volume.
find "$FIJI_HOME/jars" -name 'TrackMate-StarDist-1*.jar' -delete 2>/dev/null && true

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
    if [ -d "$FIJI_HOME/update/lib" ]; then
        cp -rv "$FIJI_HOME/update/lib/"* "$FIJI_HOME/lib/" 2>/dev/null || true
    fi
    # Clean up update directory after applying
    rm -rf "$FIJI_HOME/update/"*
    echo "[entrypoint] Updates applied successfully"
fi

# ── Remove duplicate JAR versions (post-update pass) ─────────────────────────
# Updates may have added newer versions alongside the seeded older ones.
# e.g. commons-compress-1.8.jar (seed) + commons-compress-1.27.jar (update).
deduplicate_jars "post-update"

# ── Remove SPIM_Registration (superseded by BigStitcher's multiview-reconstruction) ──
# BigStitcher installs multiview_reconstruction-*.jar which registers the same
# commands as SPIM_Registration-*.jar. Removing here (not just in Dockerfile)
# ensures the JAR is also gone from the fiji_plugins named volume, which shadows
# the image layer and would otherwise keep the old JAR across container restarts.
spim_removed=0
while IFS= read -r f; do
    echo "[entrypoint] Removing duplicate SPIM_Registration JAR: $(basename "$f")"
    rm -f "$f"
    spim_removed=$((spim_removed + 1))
done < <(find "$FIJI_HOME/plugins" -name 'SPIM_Registration*.jar' 2>/dev/null)
[ "$spim_removed" -gt 0 ] && echo "[entrypoint] Removed $spim_removed SPIM_Registration JAR(s)" || true

# ── Remove empty/stub JARs left by Fiji updater ──────────────────────────────
# Fiji's updater creates zero-byte stub files as deletion markers.
# These cause ZipException noise at startup — remove them.
empty_count=0
while IFS= read -r f; do
    echo "[entrypoint] Removing empty stub JAR: $(basename "$f")"
    rm "$f"
    empty_count=$((empty_count + 1))
done < <(find "$FIJI_HOME/plugins" "$FIJI_HOME/jars" -type f -name "*.jar" -empty 2>/dev/null)
[ "$empty_count" -gt 0 ] && echo "[entrypoint] Removed $empty_count empty stub JAR(s)" || echo "[entrypoint] No empty stub JARs found"

# ── Prepare runtime directories (tmpfs mounts start empty) ───────────────────
mkdir -p /tmp/.X11-unix
mkdir -p /home/imagentj/.fluxbox

# Single workspace so the user can't accidentally switch away from Fiji
cat > /home/imagentj/.fluxbox/init << 'EOF'
session.screen0.workspaces: 1
session.screen0.workspaceNames: Fiji
EOF

echo "[entrypoint] Starting Xvfb on display :1..."
Xvfb :1 -screen 0 2480x1200x24 -ac +extension GLX +render -noreset &
#export DISPLAY=:1
#echo "[entrypoint] Enabling keyboard repeat..."
#xset r on
#xset r rate 300 50

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

# ── Ensure langgraph-checkpoint-sqlite is installed (needed for chat persistence) ──
python3 -c "import langgraph.checkpoint.sqlite" 2>/dev/null || {
    echo "[entrypoint] Installing langgraph-checkpoint-sqlite..."
    pip install langgraph-checkpoint-sqlite -q
    echo "[entrypoint] langgraph-checkpoint-sqlite installed"
}

# ── Load persisted API keys (if any) ────────────────────────────────────────
API_KEYS_FILE=/home/imagentj/api_keys.env
if [ -f "$API_KEYS_FILE" ]; then
    echo "[entrypoint] Sourcing persisted API keys from $API_KEYS_FILE"
    . "$API_KEYS_FILE"
fi

# ── Run setup wizard if no key is configured ────────────────────────────────
if [ -z "$OPENAI_API_KEY" ] && [ -z "$OPEN_ROUTER_API_KEY" ]; then
    echo "[entrypoint] No API key found — launching setup wizard on display :1"
    python /app/setup_wizard.py || true

    if [ -f "$API_KEYS_FILE" ]; then
        echo "[entrypoint] Sourcing API keys written by setup wizard..."
        . "$API_KEYS_FILE"
    fi
fi

# ── Final key check (warn, never block) ─────────────────────────────────────
if [ -z "$OPENAI_API_KEY" ] && [ -z "$OPEN_ROUTER_API_KEY" ]; then
    echo "[entrypoint] WARNING: No API key is set. The agent will not work."
    echo "[entrypoint]          Set OPENAI_API_KEY or OPEN_ROUTER_API_KEY in .env, or"
    echo "[entrypoint]          place 'export OPENAI_API_KEY=...' in /home/imagentj/api_keys.env"
fi

# ── Launch the application ───────────────────────────────────────────────────
# PATH is already set in Dockerfile to include the conda env; no need to activate
echo "[entrypoint] Launching: $@"
exec "$@"
