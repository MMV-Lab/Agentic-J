FROM continuumio/miniconda3:latest AS base-cpu
ENV DEBIAN_FRONTEND=noninteractive
FROM base-cpu AS cpu

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
    wget unzip procps curl \
    # Locale support — ilastik4ij sets LC_ALL=en_US.UTF-8 in the subprocess
    # environment; without this the locale warning is printed to every log line
    locales \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# ── Install Fiji ──────────────────────────────────────────────────────────────
RUN wget -q https://downloads.imagej.net/fiji/latest/fiji-latest-linux64-jdk.zip -O /tmp/fiji.zip \
    && unzip -q /tmp/fiji.zip -d /opt \
    && rm /tmp/fiji.zip \
    # Rename to .app to match standard ENV variables if you have them
    && mv /opt/Fiji /opt/Fiji.app \
    # The actual binary name is fiji-linux-x64
    && chmod +x /opt/Fiji.app/fiji-linux-x64

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
    'ilastik https://sites.imagej.net/Ilastik/' \
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
        DISPLAY="" /opt/Fiji.app/fiji-linux-x64 --headless --update add-update-site "$name" "$url" || true; \
    done < /tmp/sites.txt \
    && rm /tmp/sites.txt \
    && /opt/Fiji.app/fiji-linux-x64 --headless --update update

# ── Apply staged updates into jars/ and plugins/ ─────────────────────────────
# --update update only STAGES files into update/ — it does not apply them.
# We copy here so all plugins are baked into the image with no runtime network dep.
RUN cp -a /opt/Fiji.app/update/plugins/. /opt/Fiji.app/plugins/ 2>/dev/null || true \
    && cp -a /opt/Fiji.app/update/jars/.    /opt/Fiji.app/jars/    2>/dev/null || true \
    && cp -a /opt/Fiji.app/update/macros/.  /opt/Fiji.app/macros/  2>/dev/null || true \
    && cp -a /opt/Fiji.app/update/scripts/. /opt/Fiji.app/scripts/ 2>/dev/null || true \
    && cp -a /opt/Fiji.app/update/lib/.     /opt/Fiji.app/lib/     2>/dev/null || true \
    && rm -rf /opt/Fiji.app/update/*

# ── Pin TrackMate-StarDist to 1.2.0 ──────────────────────────────────────────
# 2.0.0 has a ClassCastException in setSettings: TARGET_CHANNEL is deserialized
# as String by TrackMate's default XML marshal/unmarshal (factory doesn't override
# them), then cast to Integer — crash. 1.2.0 uses SCIJAVA_PYTHON directly
# (set to /opt/conda/envs/stardist/bin/python) and avoids the issue entirely.
# RUN rm -f /opt/Fiji.app/jars/TrackMate-StarDist-2.0.0.jar \
#     && wget -q "https://sites.imagej.net/TrackMate-StarDist/jars/TrackMate-StarDist-1.2.0.jar" \
#          -O /opt/Fiji.app/jars/TrackMate-StarDist-1.2.0.jar \
#     && echo "TrackMate-StarDist pinned to 1.2.0"

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

# ── Bundled JARs for CSBDeep and StarDist ────────────────────────────────────
# These are only on maven.scijava.org (not Maven Central), which is frequently
# unavailable. Bundled here to make builds fully offline-capable.
# Source versions: csbdeep-0.6.0, StarDist_-0.3.0-scijava, Clipper-6.4.2
COPY bundled_jars/csbdeep-0.6.0.jar           /opt/Fiji.app/jars/
COPY bundled_jars/StarDist_-0.3.0-scijava.jar /opt/Fiji.app/plugins/
COPY bundled_jars/Clipper-6.4.2.jar           /opt/Fiji.app/jars/

# ── Alternative: download from maven.scijava.org (use if bundled_jars/ is stale) ──
# Uncomment the block below and comment out the COPY lines above to re-download.
# Note: maven.scijava.org is frequently unavailable; prefer the bundled approach.
# RUN python3 - <<'PYEOF'
# import urllib.request, ssl, sys
# from pathlib import Path
#
# plugins_dir = Path('/opt/Fiji.app/plugins')
# jars_dir    = Path('/opt/Fiji.app/jars')
#
# ctx = ssl.create_default_context()
# ctx.check_hostname = False
# ctx.verify_mode    = ssl.CERT_NONE
#
# MAVEN = 'https://maven.scijava.org/content/repositories'
#
# DOWNLOADS = [
#     (jars_dir,    'csbdeep-0.6.0.jar',
#      f'{MAVEN}/releases/de/csbdresden/csbdeep/0.6.0/csbdeep-0.6.0.jar'),
#     (plugins_dir, 'StarDist_-0.3.0-scijava.jar',
#      f'{MAVEN}/releases/de/csbdresden/StarDist_/0.3.0-scijava/StarDist_-0.3.0-scijava.jar'),
#     (jars_dir,    'Clipper-6.4.2.jar',
#      f'{MAVEN}/public/de/lighti/Clipper/6.4.2/Clipper-6.4.2.jar'),
# ]
#
# all_ok = True
# for dest_dir, fname, url in DOWNLOADS:
#     dest = dest_dir / fname
#     if dest.exists():
#         print(f'[maven-dl] already present: {fname}')
#         continue
#     print(f'[maven-dl] GET {url}')
#     try:
#         req  = urllib.request.Request(url, headers={'User-Agent': 'Fiji-Docker/2.0'})
#         data = urllib.request.urlopen(req, timeout=120, context=ctx).read()
#         dest.write_bytes(data)
#         print(f'[maven-dl] saved {fname} ({len(data):,} bytes)')
#     except Exception as e:
#         print(f'[maven-dl] ERROR: {fname}: {e}', file=sys.stderr)
#         all_ok = False
#
# sys.exit(0 if all_ok else 1)
# PYEOF
#
# RUN ls /opt/Fiji.app/jars/csbdeep-*.jar \
#     && ls /opt/Fiji.app/plugins/StarDist_*.jar \
#     && echo "OK: csbdeep and StarDist_ JARs verified" \
#     || { echo "ERROR: CSBDeep or StarDist JARs missing — Maven download failed"; exit 1; }

ENV FIJI_PATH=/opt/Fiji.app

# ── Conda environment (heaviest layer - keep stable) ─────────────────────────
COPY environment.yml /tmp/environment.yml
RUN conda env create -f /tmp/environment.yml \
    && conda clean -afy \
    && rm /tmp/environment.yml

# Put the conda env on PATH so it's active by default
ENV PATH=/opt/conda/envs/local_imagent_J/bin:$PATH
ENV CONDA_DEFAULT_ENV=local_imagent_J

# ── Conda env: cellpose  (PyTorch + Cellpose, served by TrackMate-Cellpose) ───
RUN /opt/conda/bin/conda create -n cellpose python=3.10 -y \
    && /opt/conda/envs/cellpose/bin/pip install --no-cache-dir \
        torch torchvision --index-url https://download.pytorch.org/whl/cu124 \
    && /opt/conda/envs/cellpose/bin/pip install --no-cache-dir 'cellpose[gui]==3.1.1.2' \
    && /opt/conda/envs/cellpose/bin/cellpose --version \
    && /opt/conda/bin/conda clean -afy

# ── Conda env: stardist  (TensorFlow + CSBDeep + StarDist inference) ─────────
# Separate env so TF version is independent of the main Python env.
# Python 3.11 + TF 2.15 is the most stable combo for CSBDeep
# (uses tf.compat.v1 graph APIs, which became fragile in TF 2.17+).
# numpy<2 required — NumPy 2.0 breaks csbdeep's C-extension assumptions.
# tensorflow-cpu used here (CPU image); swap for tensorflow==2.15.* on GPU.
RUN /opt/conda/bin/conda create -n stardist python=3.11 -y \
    && /opt/conda/envs/stardist/bin/pip install --no-cache-dir \
        "tensorflow-cpu==2.15.*" \
        "csbdeep>=0.7.4" \
        "stardist>=0.9" \
        "numpy<2" \
    && /opt/conda/bin/conda clean -afy

# Verify the StarDist Python stack imports correctly
RUN /opt/conda/envs/stardist/bin/python -c \
    "import stardist, csbdeep, tensorflow as tf; print('[OK] StarDist Python stack: tf', tf.__version__)"

# TrackMate-StarDist looks for a Python executable via this env var
ENV SCIJAVA_PYTHON=/opt/conda/envs/stardist/bin/python

# ── Conda env: ilastik  (headless ilastik, served by TrackMate-Ilastik) ──────
# ilastik-forge ships a self-contained ilastik-core build including
# run_ilastik.sh, which the Fiji plugin invokes for headless prediction.
# Python 3.10 matches the version ilastik-forge was built against.
# this is ilastik-core ver 1.4.2rc1
RUN /opt/conda/bin/conda create -n ilastik \
        -c ilastik-forge -c conda-forge \
        ilastik-core python=3.11 -y \
    && /opt/conda/bin/conda clean -afy

# ilastik-core has no console_scripts entry point — create run_ilastik.sh wrapper.
# ilastik4ij calls this script directly for all headless prediction workflows.
RUN printf '#!/bin/bash\n# ilastik headless wrapper — invoked by ilastik4ij for all prediction workflows.\n# Logs the full command so mismatched args are visible in docker compose logs.\necho "[ilastik-wrapper] args: $*" >&2\nexec "%s" -m ilastik "$@"\n' \
        "/opt/conda/envs/ilastik/bin/python" \
        > /opt/conda/envs/ilastik/bin/run_ilastik.sh \
    && chmod +x /opt/conda/envs/ilastik/bin/run_ilastik.sh \
    && echo "[OK] ilastik headless wrapper created"

ENV ILASTIK_EXECUTABLE=/opt/conda/envs/ilastik/bin/run_ilastik.sh

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

# ── ilastik plugin preferences ────────────────────────────────────────────────
# ilastik4ij reads the executable path from ImageJ's SciJava prefs system.
# The key org.ilastik.ilastik4ij.ui.IlastikOptions.executableFile must be set
# in IJ_prefs.txt so the plugin can launch ilastik headless without the user
# having to configure it manually via Plugins → ilastik → Configure.
# The JSON file mirrors the path for any app-level code that reads it directly.
# Two persistence backends exist in Fiji depending on which PrefService is active:
#
#   LegacyIJPrefService  → ij.Prefs → ~/IJ_prefs.txt  (legacy ImageJ1 path)
#   DefaultPrefService   → java.util.prefs.Preferences → ~/.java/.userPrefs/ (Java NIO path)
#
# We write both so the executable is found regardless of which backend Fiji loads.
RUN mkdir -p /home/imagentj/.ilastik \
    # ── Backend 1: LegacyIJPrefService (~/IJ_prefs.txt) ──
    && printf '%s\n' \
        "org.ilastik.ilastik4ij.ui.IlastikOptions.executableFile=${ILASTIK_EXECUTABLE}" \
        "org.ilastik.ilastik4ij.ui.IlastikOptions.numThreads=-1" \
        "org.ilastik.ilastik4ij.ui.IlastikOptions.maxRamMb=4096" \
        >> /home/imagentj/IJ_prefs.txt \
    # ── Backend 2: DefaultPrefService (~/.java/.userPrefs/ XML) ──
    # Node path: Preferences.userNodeForPackage(IlastikOptions.class).node("IlastikOptions")
    # → /org/ilastik/ilastik4ij/ui/IlastikOptions on disk
    && mkdir -p /home/imagentj/.java/.userPrefs/org/ilastik/ilastik4ij/ui/IlastikOptions \
    && printf '%s\n' \
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>' \
        '<!DOCTYPE map SYSTEM "http://java.sun.com/dtd/preferences.dtd">' \
        '<map MAP_XML_VERSION="1.0">' \
        "  <entry key=\"executableFile\" value=\"${ILASTIK_EXECUTABLE}\"/>" \
        '  <entry key="numThreads" value="-1"/>' \
        '  <entry key="maxRamMb" value="4096"/>' \
        '</map>' \
        > /home/imagentj/.java/.userPrefs/org/ilastik/ilastik4ij/ui/IlastikOptions/prefs.xml \
    # ── JSON mirror (for any app-level code that reads it directly) ──
    && printf '{"executablePath":"%s"}\n' "${ILASTIK_EXECUTABLE}" \
        > /home/imagentj/.ilastik/fiji_plugin_prefs.json \
    && chown -R imagentj:imagentj \
        /home/imagentj/IJ_prefs.txt \
        /home/imagentj/.java \
        /home/imagentj/.ilastik

RUN mkdir -p /app/qdrant_data /home/imagentj/.cellpose \
    && chown -R imagentj:imagentj /app /home/imagentj /app/qdrant_data \
    && chown -R imagentj:imagentj /opt/Fiji.app \
    && chown -R imagentj:imagentj /opt/appose

# ── Cellpose models ───────────────────────────────────────────────────────────
# Classic models (cyto, cyto2, cyto3, nuclei, bact, etc.) are baked in from the
# local models/ folder — no network required. cpsam (Cellpose-SAM) is not yet
# in the archive; attempt a non-fatal download so it installs once the server
# recovers, without blocking the build.
RUN mkdir -p /home/imagentj/.cellpose/models
COPY models/ /home/imagentj/.cellpose/models/
# Uncomment once cellpose.org/models/cpsam is back up:
RUN HOME=/home/imagentj /opt/conda/envs/cellpose/bin/python -c \
        "from cellpose import models; models.Cellpose(model_type='cpsam')" \
    || echo "[cellpose] WARNING: cpsam unavailable — will download at first use"
RUN chown -R imagentj:imagentj /home/imagentj/.cellpose

# ── Seed home dir for named-volume persistence ────────────────────────────────
# imagentj_home is a named volume mounted at /home/imagentj. It starts empty,
# shadowing these baked-in config files. The entrypoint seeds it on first start.
RUN cp -a /home/imagentj /home/imagentj.seed

# ── Environment defaults ─────────────────────────────────────────────────────
ENV DISPLAY=:1
ENV QT_QPA_PLATFORM=xcb
ENV JAVA_HOME=/opt/conda/envs/local_imagent_J/lib/jvm
ENV HOME=/home/imagentj


COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 6080

USER imagentj

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "gui_runner.py"]