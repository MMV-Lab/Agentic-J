FROM continuumio/miniconda3:latest AS base-cpu
ENV DEBIAN_FRONTEND=noninteractive
FROM base-cpu AS cpu
ARG TARGETARCH

# ── Core system dependencies (rarely change) ─────────────────────────────────
# Split from fonts to preserve cache when adding new fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Virtual display & VNC
    xvfb x11vnc fluxbox \
    # noVNC (websocket proxy)
    novnc websockify \
    # X11 / Qt xcb dependencies
    libxcb-xinerama0 libxcb-cursor0 libxcb-keysyms1 libxcb-render-util0 \
    libxcb-icccm4 libxcb-image0 libxcb-shape0 libxkbcommon-x11-0 \
    libxcb-randr0 libxcb-xfixes0 libxcb-sync1 libxcb-glx0 \
    libegl1 libgl1 libglib2.0-0 libfontconfig1 libdbus-1-3 \
    x11-xserver-utils\
    # Java AWT / Fiji display
    libxtst6 libxi6 libxrender1 libxt6 libxext6 libx11-6 \
    # OpenGL
    libopengl0 libglx0 \
    # OpenCL CPU backend (required by CLIJ2 / BioVoxxel 3D Box without a GPU)
    # pocl-opencl-icd   — POCL software OpenCL device (CPU execution)
    # ocl-icd-libopencl1 — ICD loader runtime (libOpenCL.so.1)
    # ocl-icd-opencl-dev — provides the unversioned libOpenCL.so symlink that
    #                       JOCL needs for dlopen("libOpenCL.so") to succeed
    pocl-opencl-icd ocl-icd-libopencl1 ocl-icd-opencl-dev \
    # Utilities
    wget unzip procps curl build-essential cmake ninja-build \
    # Locale support — ilastik4ij sets LC_ALL=en_US.UTF-8 in the subprocess
    # environment; without this the locale warning is printed to every log line
    locales \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# ── Install Fiji ──────────────────────────────────────────────────────────────
RUN set -e; \
    if [ "$TARGETARCH" = "arm64" ]; then \
        FIJI_ZIP=fiji-latest-linux-arm64-jdk.zip; \
        FIJI_BINARY=fiji-linux-arm64; \
    else \
        FIJI_ZIP=fiji-latest-linux64-jdk.zip; \
        FIJI_BINARY=fiji-linux-x64; \
    fi; \
    wget -q "https://downloads.imagej.net/fiji/latest/${FIJI_ZIP}" -O /tmp/fiji.zip \
    && unzip -q /tmp/fiji.zip -d /opt \
    && rm /tmp/fiji.zip \
    # Rename to .app to match standard ENV variables if you have them
    && mv /opt/Fiji /opt/Fiji.app \
    && chmod +x "/opt/Fiji.app/${FIJI_BINARY}" /opt/Fiji.app/fiji

# ── Install plugins via update sites ─────────────────────────────────────────
# Order matters: TensorFlow → CSBDeep → StarDist (dependency chain).
# MorphoLibJ (IJPB-plugins) is a dep of TrackMate-MorphoLibJ.
RUN printf '%s\n' \
    'IJPB-plugins https://sites.imagej.net/IJPB-plugins/' \
    'TensorFlow https://sites.imagej.net/TensorFlow/' \
    'CSBDeep https://sites.imagej.net/CSBDeep/' \
    'StarDist https://sites.imagej.net/StarDist/' \
    'DeepImageJ https://sites.imagej.net/DeepImageJ/' \
    'Neuroanatomy https://sites.imagej.net/Neuroanatomy/' \
    'TrackMate-StarDist https://sites.imagej.net/TrackMate-StarDist/' \
    'TrackMate-MorphoLibJ https://sites.imagej.net/TrackMate-MorphoLibJ/' \
    'TrackMate-Ilastik https://sites.imagej.net/TrackMate-Ilastik/' \
    'TrackMate-Cellpose https://sites.imagej.net/TrackMate-Cellpose/' \
    'ImageScience https://sites.imagej.net/ImageScience/' \
    '3D_ImageJ_Suite https://sites.imagej.net/Tboudier/' \
    'BoneJ https://sites.imagej.net/BoneJ' \
    'OrientationJ http://sites.imagej.net/BIG-EPFL/' \
    'BigStitcher http://sites.imagej.net/BigStitcher/'\
    'clij https://sites.imagej.net/clij/' \
    'clij2 https://sites.imagej.net/clij2/' \
    'clijx-assistant https://sites.imagej.net/clijx-assistant/' \
    'clijx-assistant-extensions https://sites.imagej.net/clijx-assistant-extensions/' \
    'BioVoxxel http://sites.imagej.net/BioVoxxel/'\
    'BioVoxxel-3D-Box http://sites.imagej.net/bv3dbox/'\
    > /tmp/sites.txt \
    && while read -r name url; do \
        DISPLAY="" /opt/Fiji.app/fiji --headless --update add-update-site "$name" "$url" || true; \
    done < /tmp/sites.txt \
    && rm /tmp/sites.txt \
    && /opt/Fiji.app/fiji --headless --update update

# ── Apply staged updates into jars/ and plugins/ ─────────────────────────────
# --update update only STAGES files into update/ — it does not apply them.
# We copy here so all plugins are baked into the image with no runtime network dep.
RUN cp -a /opt/Fiji.app/update/plugins/. /opt/Fiji.app/plugins/ 2>/dev/null || true \
    && cp -a /opt/Fiji.app/update/jars/.    /opt/Fiji.app/jars/    2>/dev/null || true \
    && cp -a /opt/Fiji.app/update/macros/.  /opt/Fiji.app/macros/  2>/dev/null || true \
    && cp -a /opt/Fiji.app/update/scripts/. /opt/Fiji.app/scripts/ 2>/dev/null || true \
    && cp -a /opt/Fiji.app/update/lib/.     /opt/Fiji.app/lib/     2>/dev/null || true \
    && rm -rf /opt/Fiji.app/update/*

# ── Patch TrackMate-StarDist 2.0.0 ClassCastException ────────────────────────
# 2.0.0 has the correct TrackMate 8.x API (4-arg getDetector) but no
# marshal/unmarshal overrides: TARGET_CHANNEL is saved as String in XML, then
# cast to Integer in setSettings() and getDetector() → ClassCastException.
# Fix: use javassist to insertBefore in both methods, converting String→Integer.
# 1.2.0 (wrong API for TM 8.x) is left absent so AbstractMethodError doesn't recur.
COPY patch_stardist/PatchStarDist.java /tmp/PatchStarDist.java
RUN set -e \
    && FIJI=/opt/Fiji.app \
    # Locate the JDK bundled with Fiji
    && JAVA_BIN=$(find "$FIJI/java" -type f -name 'java' 2>/dev/null | head -1) \
    && JAVAC_BIN=$(find "$FIJI/java" -type f -name 'javac' 2>/dev/null | head -1) \
    && [ -n "$JAVA_BIN"  ] || JAVA_BIN=java \
    && [ -n "$JAVAC_BIN" ] || JAVAC_BIN=javac \
    && echo "[patch] Using java: $JAVA_BIN  javac: $JAVAC_BIN" \
    # Locate javassist — already in Fiji after plugins are installed; fall back to Maven Central
    && JAVASSIST=$(find "$FIJI" -name 'javassist*.jar' 2>/dev/null | head -1) \
    && if [ -z "$JAVASSIST" ]; then \
         echo "[patch] javassist not found in Fiji — downloading from Maven Central"; \
         wget -q -O /tmp/javassist.jar \
             "https://repo1.maven.org/maven2/org/javassist/javassist/3.29.2-GA/javassist-3.29.2-GA.jar"; \
         JAVASSIST=/tmp/javassist.jar; \
       fi \
    && echo "[patch] javassist: $JAVASSIST" \
    # Compile PatchStarDist.java (also updates the JAR via java.util.zip — no 'zip' CLI needed)
    && mkdir -p /tmp/patch-classes \
    && $JAVAC_BIN -cp "$JAVASSIST" /tmp/PatchStarDist.java -d /tmp/patch-classes \
    && $JAVA_BIN  -cp "/tmp/patch-classes:$JAVASSIST" PatchStarDist \
    && rm -rf /tmp/patch-classes /tmp/stardist-patched-classes /tmp/PatchStarDist.java \
              /tmp/javassist.jar 2>/dev/null || true \
    && echo "[patch] TrackMate-StarDist 2.0.0 ClassCastException fix applied" \
    # Save a copy of the patched JAR outside the fiji_jars volume mount point.
    # The entrypoint uses this to re-apply the patch after volume seeding, because
    # _seed_volume skips existing files so the unpatched JAR persists across rebuilds.
    && mkdir -p /opt/fiji-patches \
    && cp /opt/Fiji.app/jars/TrackMate-StarDist-2.0.0.jar /opt/fiji-patches/TrackMate-StarDist-2.0.0.jar.patched

# ── Remove SPIM_Registration.jar (superseded by BigStitcher's multiview-reconstruction) ──
# BigStitcher installs multiview-reconstruction.jar which registers the same menu
# commands as the base Fiji SPIM_Registration.jar, causing duplicate command warnings.
RUN find /opt/Fiji.app/plugins -name 'SPIM_Registration*.jar' -delete \
    && echo "SPIM_Registration JAR(s) removed (superseded by multiview-reconstruction)"

# ── Fix 3D ImageJ Suite: move mcib3d-core to jars/ ───────────────────────────
# The Tboudier update site places mcib3d-core under plugins/3D_ImageJ_Suite/.
# When it stays in plugins/, ImageJ's plugin scanner evaluates plugin classes in
# mcib3d_plugins.jar before the subdirectory JARs are fully on the classpath,
# causing NoClassDefFoundError for every plugin except the trivial About_ class.
# Moving mcib3d-core to jars/ makes it a first-class classpath entry loaded
# before any plugin scanning begins, so all 3D Suite plugins register correctly.
RUN find /opt/Fiji.app/plugins -name 'mcib3d-core*.jar' \
        -exec mv -v {} /opt/Fiji.app/jars/ \; 2>/dev/null || true \
    && echo "=== 3D Suite JARs after relocation ===" \
    && find /opt/Fiji.app -name 'mcib3d*' 2>/dev/null | sort \
    && echo "=== imagescience JARs ===" \
    && find /opt/Fiji.app -name 'imagescience*' 2>/dev/null | sort

# ── Direct Maven download for CSBDeep and StarDist JARs ──────────────────────
# The Fiji update sites for these two plugins have stale file links (all 404s).
# URLs verified from maven.scijava.org (2026-04).
#   csbdeep-0.6.0.jar         → jars/   (SciJava @Plugin library, not a menu plugin)
#   StarDist_-0.3.0-scijava.jar → plugins/
#   Clipper-6.4.2.jar         → jars/   (required runtime dep of StarDist)
RUN python3 - <<'PYEOF'
import urllib.request, ssl, sys
from pathlib import Path

plugins_dir = Path('/opt/Fiji.app/plugins')
jars_dir    = Path('/opt/Fiji.app/jars')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode    = ssl.CERT_NONE

MAVEN = 'https://maven.scijava.org/content/repositories'

DOWNLOADS = [
    (jars_dir,    'csbdeep-0.6.0.jar',
     f'{MAVEN}/releases/de/csbdresden/csbdeep/0.6.0/csbdeep-0.6.0.jar'),
    (plugins_dir, 'StarDist_-0.3.0-scijava.jar',
     f'{MAVEN}/releases/de/csbdresden/StarDist_/0.3.0-scijava/StarDist_-0.3.0-scijava.jar'),
    (jars_dir,    'Clipper-6.4.2.jar',
     f'{MAVEN}/public/de/lighti/Clipper/6.4.2/Clipper-6.4.2.jar'),
]

all_ok = True
for dest_dir, fname, url in DOWNLOADS:
    dest = dest_dir / fname
    if dest.exists():
        print(f'[maven-dl] already present: {fname}')
        continue
    print(f'[maven-dl] GET {url}')
    try:
        req  = urllib.request.Request(url, headers={'User-Agent': 'Fiji-Docker/2.0'})
        data = urllib.request.urlopen(req, timeout=120, context=ctx).read()
        dest.write_bytes(data)
        print(f'[maven-dl] saved {fname} ({len(data):,} bytes)')
    except Exception as e:
        print(f'[maven-dl] ERROR: {fname}: {e}', file=sys.stderr)
        all_ok = False

sys.exit(0 if all_ok else 1)
PYEOF

# Verify JARs are present (CSBDeep lives in jars/, not plugins/)
RUN ls /opt/Fiji.app/jars/csbdeep-*.jar \
    && ls /opt/Fiji.app/plugins/StarDist_*.jar \
    && echo "OK: csbdeep and StarDist_ JARs verified" \
    || { echo "ERROR: CSBDeep or StarDist JARs missing — Maven download failed"; exit 1; }

# ── For aarch64, install CSBDeep linux/arm64 TensorFlow Java single-JAR patch ────────────
# The upstream CSBDeep Fiji JAR depends on TensorFlow Java 1.x JNI artifacts
# that do not ship linux/aarch64 native libraries. Use the prebuilt single JAR
# with an isolated TensorFlow Java 1.1.0 runtime (TensorFlow core 2.18.0)
# bundled inside.
ARG TARGETARCH
ARG CSBDEEP_TFJAVA_JAR_URL="https://github.com/audreyeternal/CSBDeep/releases/download/csbdeep-tfjava-arm64-v0.6.0/csbdeep-0.6.0-tfjava-linux-arm64.jar"
ARG CSBDEEP_TFJAVA_JAR_SHA256="065702602843af513ebcff8f423903d33755e6d2285456360f6a286444d8704e"
RUN set -e; \
    arch="${TARGETARCH:-$(uname -m)}"; \
    case "$arch" in \
        arm64|aarch64) \
            echo "[csbdeep] Installing TensorFlow Java linux/arm64 single-JAR patch"; \
            wget -q -O /tmp/csbdeep-0.6.0-tfjava-linux-arm64.jar "$CSBDEEP_TFJAVA_JAR_URL"; \
            echo "$CSBDEEP_TFJAVA_JAR_SHA256  /tmp/csbdeep-0.6.0-tfjava-linux-arm64.jar" | sha256sum -c -; \
            cp /tmp/csbdeep-0.6.0-tfjava-linux-arm64.jar /opt/Fiji.app/jars/csbdeep-0.6.0.jar; \
            mkdir -p /opt/fiji-patches; \
            cp /tmp/csbdeep-0.6.0-tfjava-linux-arm64.jar /opt/fiji-patches/csbdeep-0.6.0-tfjava-linux-arm64.jar; \
            rm -f /tmp/csbdeep-0.6.0-tfjava-linux-arm64.jar; \
            ;; \
        amd64|x86_64) \
            echo "[csbdeep] Skipping linux/arm64 CSBDeep patch on $arch"; \
            ;; \
        *) \
            echo "[csbdeep] Skipping linux/arm64 CSBDeep patch on unsupported architecture: $arch"; \
            ;; \
    esac

ENV FIJI_PATH=/opt/Fiji.app

# ── Conda environment (heaviest layer - keep stable) ─────────────────────────
COPY environment.yml /tmp/environment.yml
RUN conda env create -f /tmp/environment.yml \
    && conda clean -afy \
    && rm /tmp/environment.yml

# Put the conda env on PATH so it's active by default
ENV PATH=/opt/conda/envs/local_imagent_J/bin:$PATH
ENV CONDA_DEFAULT_ENV=local_imagent_J

# ── Conda env: cellpose  (PyTorch + Cellpose + Omnipose, served by TrackMate-Cellpose and TrackMate-Omnipose) ───
# Omnipose 1.x is built on cellpose 3.x, so they share one env.
# The micromamba shim routes both '-n cellpose' and '-n omnipose' here.
RUN /opt/conda/bin/conda create -n cellpose python=3.10 -y \
    && if [ "$TARGETARCH" = "arm64" ]; then \
        /opt/conda/envs/cellpose/bin/pip install --no-cache-dir torch torchvision; \
    else \
        /opt/conda/envs/cellpose/bin/pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu; \
    fi \
    && /opt/conda/envs/cellpose/bin/pip install --no-cache-dir 'cellpose[gui]==3.1.1.2' \
    && /opt/conda/envs/cellpose/bin/pip install --no-cache-dir 'omnipose==1.1.4' \
    && /opt/conda/envs/cellpose/bin/cellpose --version \
    && /opt/conda/bin/conda clean -afy \
    && printf '#!/bin/bash\nexec /opt/conda/envs/cellpose/bin/cellpose "$@"\n' > /opt/conda/bin/cellpose \
    && chmod +x /opt/conda/bin/cellpose

# ── Conda env: cellpose4  (Cellpose 4.x + SAM, served by TrackMate Cellpose-SAM) ──
# Separate env so cellpose 3.x (regular detection) and 4.x (SAM) can coexist.
# TrackMate's CondaCLIConfigurator lists all conda envs in a dropdown — the user
# selects 'cellpose4' in the Cellpose-SAM detector panel.
# The micromamba shim routes '-n cellpose4' → /opt/conda/envs/cellpose4.
RUN /opt/conda/bin/conda create -n cellpose4 python=3.11 -y \
    && if [ "$TARGETARCH" = "arm64" ]; then \
        /opt/conda/envs/cellpose4/bin/pip install --no-cache-dir torch torchvision; \
    else \
        /opt/conda/envs/cellpose4/bin/pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu; \
    fi \
    && /opt/conda/envs/cellpose4/bin/pip install --no-cache-dir 'cellpose[gui]>=4.0' \
    && /opt/conda/envs/cellpose4/bin/cellpose --version \
    && /opt/conda/bin/conda clean -afy

# ── Conda env: stardist  (TensorFlow + CSBDeep + StarDist inference) ─────────
# Separate env so TF version is independent of the main Python env.
# Python 3.11 + TF 2.15 is the most stable combo for CSBDeep
# (uses tf.compat.v1 graph APIs, which became fragile in TF 2.17+).
# numpy<2 required — NumPy 2.0 breaks csbdeep's C-extension assumptions.
# BuildKit provides TARGETARCH; arm64 uses the linux/aarch64 TensorFlow package
# path, while amd64 keeps tensorflow-cpu for native x86_64 hosts.
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        TF_PACKAGE='tensorflow==2.15.*'; \
    else \
        TF_PACKAGE='tensorflow-cpu==2.15.*'; \
    fi \
    && /opt/conda/bin/conda create -n stardist python=3.11 -y \
    && /opt/conda/envs/stardist/bin/pip install --no-cache-dir \
        "$TF_PACKAGE" \
        "csbdeep>=0.7.4" \
        "stardist>=0.9" \
        "numpy<2" \
    && /opt/conda/bin/conda clean -afy

# Verify the StarDist Python stack imports correctly
RUN /opt/conda/envs/stardist/bin/python -c \
    "import stardist, csbdeep, tensorflow as tf; print('[OK] StarDist Python stack: tf', tf.__version__)"

# TrackMate-StarDist looks for a Python executable via this env var
ENV SCIJAVA_PYTHON=/opt/conda/envs/stardist/bin/python

# ── DeepImageJ / APPOSE environment configuration ────────────────────────────
# DeepImageJ 3.x uses APPOSE (via dl-modelrunner) to run Python inference.
# APPOSE creates ONE environment per framework (TF, PyTorch) stored under
# APPOSE_HOME — not one per model.  We redirect APPOSE_HOME to a stable path
# under /opt so environments are baked into the image and never recreated at
# runtime.
#
# APPOSE also calls micromamba (our shim) when it needs to build an env.
# The micromamba_shim.sh already intercepts these calls; the APPOSE envs will
# be created with generated hash-names which the shim forwards as-is via conda.
#
# We pre-create a minimal DeepImageJ APPOSE env directory so the plugin finds
# a writeable home without trying to create it inside a read-only layer.
ENV APPOSE_HOME=/opt/appose
RUN mkdir -p /opt/appose \
    && chmod 777 /opt/appose

# ── TrackMate micromamba shim ─────────────────────────────────────────────────
# TrackMate-Cellpose hardcodes the micromamba path. Older versions use
# /usr/local/opt/micromamba/bin/micromamba; newer versions use /opt/micromamba/bin/micromamba.
# Install the shim at both locations so either version works.
COPY micromamba_shim.sh /usr/local/opt/micromamba/bin/micromamba
RUN chmod +x /usr/local/opt/micromamba/bin/micromamba \
    && ln -sf micromamba /usr/local/opt/micromamba/bin/conda \
    && mkdir -p /opt/micromamba/bin \
    && cp /usr/local/opt/micromamba/bin/micromamba /opt/micromamba/bin/micromamba \
    && chmod +x /opt/micromamba/bin/micromamba \
    && ln -sf micromamba /opt/micromamba/bin/conda

# ── Fonts (separate layer - changes here won't invalidate conda cache) ───────
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f -v

# ── Non-root user ─────────────────────────────────────────────────────────────
RUN groupadd -g 1000 imagentj \
    && useradd -u 1000 -g imagentj -m -d /home/imagentj -s /bin/bash imagentj
    
# ── Application code ─────────────────────────────────────────────────────────
WORKDIR /app
COPY . /app

# Use keys_template.py as keys.py (keys.py is .dockerignored since it has real secrets)
RUN cp /app/src/config/keys_template.py /app/src/config/keys.py

# Ensure the app user owns everything it needs to write to (including qdrant_data directory)
# ── TrackMate v8 conda configuration ─────────────────────────────────────────
# TrackMate v8 uses a unified conda framework for all Python-based detectors.
# Each plugin activates its own named env:
#   TrackMate-Cellpose  → env 'cellpose'
#   TrackMate-StarDist  → env 'stardist'
# The micromamba shim (below) provides a fallback for plugins that still
# hardcode the micromamba path.
RUN mkdir -p /home/imagentj/.imagej \
    && printf '[trackmate]\ncondaRootPrefix=/opt/conda\ncondaExecutable=/opt/conda/bin/conda\n' \
        > /home/imagentj/.imagej/trackmate-conda.prefs \
    && chown -R imagentj:imagentj /home/imagentj/.imagej

RUN mkdir -p /app/qdrant_data /home/imagentj/.cellpose /home/imagentj/.cache \
    && chown -R imagentj:imagentj /app /home/imagentj /app/qdrant_data \
    && chown -R imagentj:imagentj /opt/Fiji.app \
    && chown -R imagentj:imagentj /opt/appose

# ── Cellpose models ───────────────────────────────────────────────────────────
# Models are NOT baked into the image — docker-compose bind-mounts ./models to
# /home/imagentj/.cellpose/models at runtime 
# Create the directory so the seed has the correct structure and ownership.
RUN mkdir -p /home/imagentj/.cellpose/models \
    && chown -R imagentj:imagentj /home/imagentj/.cellpose

# ── Seed home dir for named-volume persistence ────────────────────────────────
# imagentj_home is a named volume mounted at /home/imagentj. It starts empty,
# shadowing these baked-in config files. The entrypoint seeds it on first start.
RUN cp -a /home/imagentj /home/imagentj.seed

# ── Environment defaults ─────────────────────────────────────────────────────
ENV DISPLAY=:1
ENV QT_QPA_PLATFORM=xcb
ENV JAVA_HOME=/opt/conda/envs/local_imagent_J
ENV HOME=/home/imagentj


COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 6080

USER imagentj

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "gui_runner.py"]
