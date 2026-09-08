FROM continuumio/miniconda3:latest AS base-cpu
ENV DEBIAN_FRONTEND=noninteractive
FROM base-cpu AS cpu
ARG TARGETARCH
# Set USE_GPU=true at build time to install CUDA-enabled PyTorch / TensorFlow (amd64 only).
# CUDA_TAG selects the PyTorch wheel index. torch==2.11.0 wheels are published ONLY for
# cu126 and cu128 — older tags (cu118/cu121/cu124) top out at torch 2.6.0 and fail the
# build with "No matching distribution found for torch==2.11.0". Default cu126 needs
# driver 560+.
# tensorflow[and-cuda]==2.15.1 bundles its own CUDA 12.2 libs (driver 535+); the
# effective driver minimum is therefore set by the torch CUDA tag.
# Valid overrides (must have a torch 2.11.0 build):
#   cu126 → driver 560+  (default; widest driver compatibility for torch 2.11.0)
#   cu128 → driver 570+  (newest CUDA; RTX 50xx / freshest drivers)
ARG USE_GPU=false
ARG CUDA_TAG=cu126

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
    # OpenGL — libgl1-mesa-dri provides the llvmpipe software renderer that
    # napari/vispy need under headless Xvfb (no GPU); paired with
    # LIBGL_ALWAYS_SOFTWARE=1 set below.
    libopengl0 libglx0 libgl1-mesa-dri \
    # OpenCL CPU backend (required by CLIJ2 / BioVoxxel 3D Box without a GPU)
    # pocl-opencl-icd   — POCL software OpenCL device (CPU execution)
    # ocl-icd-libopencl1 — ICD loader runtime (libOpenCL.so.1)
    # ocl-icd-opencl-dev — provides the unversioned libOpenCL.so symlink that
    #                       JOCL needs for dlopen("libOpenCL.so") to succeed
    pocl-opencl-icd ocl-icd-libopencl1 ocl-icd-opencl-dev \
    # Utilities
    wget unzip procps curl build-essential cmake ninja-build\
    # Locale support — ilastik4ij sets LC_ALL=en_US.UTF-8 in the subprocess
    # environment; without this the locale warning is printed to every log line
    locales \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# ── Register the NVIDIA OpenCL driver (GPU builds only) ──────────────────────
# CLIJ/CLIJ2 reach the GPU through OpenCL, NOT CUDA — a separate stack from the
# torch/TensorFlow wheels below. The container runtime (CDI) already mounts
# libnvidia-opencl.so.1 into the GPU container, but it does NOT write the ICD
# registration file, and the OpenCL loader discovers platforms ONLY by reading
# /etc/OpenCL/vendors/*.icd. Without this line the sole registered vendor is
# pocl.icd, so CLIJ2 silently enumerates just the CPU and every "GPU-accelerated"
# CLIJ call runs on POCL — usually SLOWER than plain ImageJ, because the
# host<->device copies are paid without any GPU speedup in return.
#
# Verified in the live gpu-local container (2026-08-03): before, CLIJ reported
# one device, "cpu-haswell-AMD EPYC 7742"; after adding this file it reported
# 8x "NVIDIA A100-SXM4-40GB" plus the CPU.
#
# pocl.icd is deliberately kept as the fallback (and is the only vendor on CPU
# builds); CLIJ picks the best available device.
RUN if [ "$USE_GPU" = "true" ] && [ "$TARGETARCH" != "arm64" ]; then \
        mkdir -p /etc/OpenCL/vendors \
        && echo "libnvidia-opencl.so.1" > /etc/OpenCL/vendors/nvidia.icd; \
    fi

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

# ── Fix SLF4J startup warnings ────────────────────────────────────────────────
# Fiji ships SLF4J 2.x API (ServiceLoader-based providers) but logback-classic
# 1.2.x uses the old StaticLoggerBinder mechanism from SLF4J 1.7.x, which 2.x
# ignores — producing the "No SLF4J providers" and "Ignoring binding" warnings.
# Remove the incompatible logback JAR and add the proper 2.x NOP provider.
RUN rm -f /opt/Fiji.app/jars/logback-classic-1.2*.jar \
    && wget -q "https://repo1.maven.org/maven2/org/slf4j/slf4j-nop/2.0.16/slf4j-nop-2.0.16.jar" \
         -O /opt/Fiji.app/jars/slf4j-nop-2.0.16.jar \
    && mkdir -p /opt/fiji-patches \
    && cp /opt/Fiji.app/jars/slf4j-nop-2.0.16.jar /opt/fiji-patches/slf4j-nop-2.0.16.jar \
    && echo "[slf4j] logback-classic-1.2.x removed; slf4j-nop-2.0.16 installed"

# ── Bundled JARs for CSBDeep and StarDist ────────────────────────────────────
# These are only on maven.scijava.org (not Maven Central), which is frequently
# unavailable. Bundled here to make builds fully offline-capable.
# Source versions: csbdeep-0.6.0, StarDist_-0.3.0-scijava, Clipper-6.4.2
COPY bundled_jars/csbdeep-0.6.0.jar           /opt/Fiji.app/jars/
COPY bundled_jars/StarDist_-0.3.0-scijava.jar /opt/Fiji.app/plugins/
COPY bundled_jars/Clipper-6.4.2.jar           /opt/Fiji.app/jars/

# ── BIOP Cellpose wrapper (from the PTBIOP update site) ──────────────────────
# ch.epfl.biop.wrappers.cellpose.* — runs Cellpose directly and returns the
# label image in-process (cp.cellpose_imp), without TrackMate. We bundle just
# this one jar (sha256 eb0b10d8686ae32f7364dddacb01c3dae2491eb330a97fbc9bcef37cce9fa842)
# rather than enabling the whole PTBIOP site, to avoid version drift against the
# carefully-pinned jars in this image. SciJava discovers the `Cellpose` command
# from the classpath, so the menu entry (Plugins > BIOP > Cellpose) appears.
# See skills/cellpose_documentation/. Conda activation relies on BASH_ENV
# (set in src/imagentj/imagej_context.py) pointing at conda.sh.
COPY bundled_jars/ijl-utilities-wrappers-0.12.1.jar /opt/Fiji.app/jars/

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

# ── fastmcp client for the generic MCP host adapter ──────────────────────────
# src/imagentj/tools/mcp_host_tools.py runs INSIDE this app env and speaks MCP
# (stdio/HTTP) to configured servers via `from fastmcp import Client`. It needs
# the fastmcp *client* here; the napari *server* gets its own fastmcp in the
# isolated env below. Separate RUN keeps the heavy env-create layer cache-stable.
RUN /opt/conda/envs/local_imagent_J/bin/pip install --no-cache-dir "fastmcp>=2.10.3,<3" \
    && /opt/conda/bin/conda clean -afy

# ── Conda env: napari-mcp  (in-container MCP visualisation server) ────────────
# Isolated like the cellpose/stardist envs so napari's large, version-pinned
# dependency tree cannot conflict with the py3.13 app env. The `napari-mcp`
# stdio server (entry point napari_mcp.server:main) creates its napari Viewer
# LAZILY via ensure_viewer() — only when a napari tool is first called — so this
# env stays idle (no window) until the agent actually uses napari.
RUN /opt/conda/bin/conda create -n napari-mcp python=3.11 -y \
    && /opt/conda/envs/napari-mcp/bin/pip install --no-cache-dir \
        "napari[pyqt6]" \
        "napari-mcp" \
        "fastmcp>=2.10.3,<3" \
    && QT_QPA_PLATFORM=offscreen /opt/conda/envs/napari-mcp/bin/python -c \
        "import napari, napari_mcp, fastmcp; print('napari', napari.__version__)" \
    && /opt/conda/bin/conda clean -afy

# Patch napari-mcp for Agent J's persistent, interactive viewer (see
# patch_napari_mcp/patch_qt_helpers.py): survive the window close button (don't
# shut the server down) and keep the Qt event pump alive on any viewer reopen
# (e.g. via add_layer, not just init_viewer) so the reopened window stays
# responsive to mouse/keyboard. Fails the build if upstream source drifts.
COPY patch_napari_mcp/patch_qt_helpers.py /tmp/patch_qt_helpers.py
RUN /opt/conda/envs/napari-mcp/bin/python /tmp/patch_qt_helpers.py && rm /tmp/patch_qt_helpers.py

# ── micro_sam ("Segment Anything for Microscopy") into the napari-mcp env ─────
# Installed INTO the napari env (not a separate one) so it registers as a real
# napari plugin (GUI: Plugins > Segment Anything for Microscopy) AND is importable
# by both the interactive viewer (via napari-mcp execute_code) and the headless
# batch route (python_data_analyst, `# imagentj-env: napari-mcp`). Pulls torch +
# segment-anything + torch_em + elf via conda-forge. mobile_sam (pip, from git) is
# only needed for the tiny `vit_t*` backbones — the fastest option on CPU; the
# base default `vit_b_lm` works without it.
#
# GPU: conda-forge's micro_sam pulls a CPU-ONLY torch, so on a GPU build we swap it
# for the CUDA wheels (same torch/torchvision pin + CUDA_TAG as the cellpose envs) so
# micro_sam uses the GPU. On a CPU build (USE_GPU=false, the default) or arm64 the
# working conda CPU torch is left untouched — micro_sam still runs, just on CPU
# (device auto-selects via torch.cuda.is_available()). The swap pulls torch's
# nvidia-*-cu12 CUDA runtime wheels as dependencies — do NOT pass --no-deps or torch
# fails to import with "libcudart.so.12: cannot open shared object file". --force-
# reinstall is needed so BOTH torch and torchvision move off the conda CPU build. The
# build-time check asserts it is a CUDA *build*, not that a GPU is present (the build
# host may have none). Validated: torch 2.11.0+cu126 + torchvision 0.26.0+cu126 import
# cleanly and micro_sam still imports afterwards.
RUN CONDA_SOLVER=libmamba /opt/conda/bin/conda install -n napari-mcp -c conda-forge micro_sam -y \
    && /opt/conda/envs/napari-mcp/bin/pip install --no-cache-dir \
        "git+https://github.com/ChaoningZhang/MobileSAM.git" \
    && if [ "$USE_GPU" = "true" ] && [ "$TARGETARCH" != "arm64" ]; then \
           /opt/conda/envs/napari-mcp/bin/pip install --no-cache-dir --force-reinstall \
               'torch==2.11.0' 'torchvision==0.26.0' \
               --index-url https://download.pytorch.org/whl/${CUDA_TAG} \
           && /opt/conda/envs/napari-mcp/bin/python -c \
               "import torch; assert torch.version.cuda, 'expected a CUDA torch build in the GPU image'"; \
       fi \
    && /opt/conda/envs/napari-mcp/bin/python -c \
        "import micro_sam, mobile_sam, torch; print('micro_sam', micro_sam.__version__, 'torch', torch.__version__, 'cuda_build', torch.version.cuda)" \
    && /opt/conda/bin/conda clean -afy

# Repair a half-finished Pillow upgrade: the torch/torchvision --force-reinstall above
# pulls Pillow as a torchvision dependency and can leave a metadata-less
# `pillow-<ver>.dist-info` ghost (only an sboms/ subdir, no METADATA). huggingface_hub
# probes Pillow's version on import, so importlib.metadata trips over the ghost with
# `MetadataNotFound` and takes down the whole `micro_sam.sam_annotator` import chain —
# at RUNTIME, not build (the top-level `import micro_sam` above doesn't exercise it).
# Delete any Pillow dist-info without a METADATA file, then assert the annotator (the
# part that crashed for users) actually imports, so a regression fails the build here.
RUN for d in /opt/conda/envs/napari-mcp/lib/python3.11/site-packages/[Pp]illow-*.dist-info; do \
        if [ -e "$d" ] && [ ! -s "$d/METADATA" ]; then echo "removing ghost dist-info: $d"; rm -rf "$d"; fi; \
    done; \
    QT_QPA_PLATFORM=offscreen /opt/conda/envs/napari-mcp/bin/python -c \
        "import micro_sam.sam_annotator; from micro_sam.sam_annotator.training_ui import TrainingWidget; print('micro_sam.sam_annotator import OK')"

# napari/vispy fall back to llvmpipe software GL under headless Xvfb (no GPU).
ENV LIBGL_ALWAYS_SOFTWARE=1

# ── Conda env: cellpose  (PyTorch + Cellpose + Omnipose, served by TrackMate-Cellpose and TrackMate-Omnipose) ───
# Omnipose 1.x is built on cellpose 3.x, so they share one env.
# The micromamba shim routes both '-n cellpose' and '-n omnipose' here.
# Snapshot (2026-04-30): Python 3.10.20, cellpose 3.1.1.2, omnipose 1.1.4, torch 2.11.0+cpu|cu124
# tifffile is bumped to 2025.5.10 AFTER cellpose installs: cellpose[gui] pins the
# old 2023.2.28, which calls ndarray.newbyteorder() (removed in NumPy 2.0) when
# reading the big-endian ('MM') TIFFs that ImageJ/Fiji writes. The BIOP Cellpose
# wrapper feeds cellpose an ImageJ-written TIFF, so without the bump cellpose
# crashes on read. Done as a separate pip call so the resolver doesn't fight
# aicsimageio's stale <2023.3.15 pin (aicsimageio is not on the cellpose read path).
RUN /opt/conda/bin/conda create -n cellpose python=3.10 -y \
    && if [ "$TARGETARCH" = "arm64" ]; then \
        /opt/conda/envs/cellpose/bin/pip install --no-cache-dir \
            'torch==2.11.0' 'torchvision==0.26.0'; \
    elif [ "$USE_GPU" = "true" ]; then \
        /opt/conda/envs/cellpose/bin/pip install --no-cache-dir \
            'torch==2.11.0' 'torchvision==0.26.0' \
            --index-url https://download.pytorch.org/whl/${CUDA_TAG}; \
    else \
        /opt/conda/envs/cellpose/bin/pip install --no-cache-dir \
            'torch==2.11.0' 'torchvision==0.26.0' \
            --index-url https://download.pytorch.org/whl/cpu; \
    fi \
    && /opt/conda/envs/cellpose/bin/pip install --no-cache-dir \
        'cellpose[gui]==3.1.1.2' \
        'omnipose==1.1.4' \
        'langchain-core==1.2.16' \
        'langgraph-checkpoint-sqlite==3.0.3' \
        'pydantic==2.12.5' \
    && /opt/conda/envs/cellpose/bin/pip install --no-cache-dir 'tifffile==2025.5.10' \
    && /opt/conda/envs/cellpose/bin/cellpose --version \
    && /opt/conda/bin/conda clean -afy \
    && printf '#!/bin/bash\nexec /opt/conda/envs/cellpose/bin/cellpose "$@"\n' > /opt/conda/bin/cellpose \
    && chmod +x /opt/conda/bin/cellpose

# ── Conda env: cellpose4  (Cellpose 4.x + SAM, served by TrackMate Cellpose-SAM) ──
# Separate env so cellpose 3.x (regular detection) and 4.x (SAM) can coexist.
# TrackMate's CondaCLIConfigurator lists all conda envs in a dropdown — the user
# selects 'cellpose4' in the Cellpose-SAM detector panel.
# The micromamba shim routes '-n cellpose4' → /opt/conda/envs/cellpose4.
# Snapshot (2026-04-30): Python 3.11.15, cellpose 4.1.1, segment-anything 1.0, torch 2.11.0+cpu|cu124
RUN /opt/conda/bin/conda create -n cellpose4 python=3.11 -y \
    && if [ "$TARGETARCH" = "arm64" ]; then \
        /opt/conda/envs/cellpose4/bin/pip install --no-cache-dir \
            'torch==2.11.0' 'torchvision==0.26.0'; \
    elif [ "$USE_GPU" = "true" ]; then \
        /opt/conda/envs/cellpose4/bin/pip install --no-cache-dir \
            'torch==2.11.0' 'torchvision==0.26.0' \
            --index-url https://download.pytorch.org/whl/${CUDA_TAG}; \
    else \
        /opt/conda/envs/cellpose4/bin/pip install --no-cache-dir \
            'torch==2.11.0' 'torchvision==0.26.0' \
            --index-url https://download.pytorch.org/whl/cpu; \
    fi \
    && /opt/conda/envs/cellpose4/bin/pip install --no-cache-dir \
        'cellpose[gui]==4.1.1' \
        'segment-anything==1.0' \
        'langchain-core==1.2.16' \
        'langgraph-checkpoint-sqlite==3.0.3' \
        'pydantic==2.12.5' \
    && /opt/conda/envs/cellpose4/bin/cellpose --version \
    && /opt/conda/bin/conda clean -afy

# ── Conda env: stardist  (TensorFlow + CSBDeep + StarDist inference) ─────────
# Separate env so TF version is independent of the main Python env.
# Python 3.11 + TF 2.15 is the most stable combo for CSBDeep
# (uses tf.compat.v1 graph APIs, which became fragile in TF 2.17+).
# Snapshot (2026-04-30): Python 3.11.15, stardist 0.9.2, csbdeep 0.8.2,
#   tensorflow[-cpu|[and-cuda]] 2.15.1, numpy 1.26.4
# arm64 uses generic 'tensorflow' (no -cpu suffix) — the linux/aarch64 TF wheel
# is not published under the tensorflow-cpu name.
# GPU (amd64 only): tensorflow[and-cuda] bundles the CUDA 12.2 runtime libraries
# so no system CUDA install is needed in the container.
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        TF_PACKAGE='tensorflow==2.15.1'; \
    elif [ "$USE_GPU" = "true" ]; then \
        TF_PACKAGE='tensorflow[and-cuda]==2.15.1'; \
    else \
        TF_PACKAGE='tensorflow-cpu==2.15.1'; \
    fi \
    && /opt/conda/bin/conda create -n stardist python=3.11 -y \
    && /opt/conda/envs/stardist/bin/pip install --no-cache-dir \
        "$TF_PACKAGE" \
        "csbdeep==0.8.2" \
        "stardist==0.9.2" \
        "numpy==1.26.4" \
        "langchain-core==1.2.16" \
        "langgraph-checkpoint-sqlite==3.0.3" \
        "pydantic==2.12.5" \
    && /opt/conda/bin/conda clean -afy

# Verify the StarDist Python stack imports correctly
RUN /opt/conda/envs/stardist/bin/python -c \
    "import stardist, csbdeep, tensorflow as tf; print('[OK] StarDist Python stack: tf', tf.__version__)"

# TrackMate-StarDist looks for a Python executable via this env var
ENV SCIJAVA_PYTHON=/opt/conda/envs/stardist/bin/python

# ── BrainGlobe environment ───────────────────────────────────────────────────
# Isolated because the full brainglobe meta-package drags in napari[all] +
# PyQt6 + vtk + keras (7.2 GB), which collides with the main env's PySide6 GUI
# and forces further downgrades. We install the HEADLESS subset instead (1.3 GB):
# atlas access + whole-brain registration, no 3D viewer, no cellfinder.
#
# The python_coder selects this env with a first-line magic comment:
#     # imagentj-env: brainglobe
# See _CONDA_ENVS in src/imagentj/tools/analyst_tools.py.
RUN /opt/conda/bin/conda create -n brainglobe python=3.12 -y \
    && /opt/conda/envs/brainglobe/bin/pip install --no-cache-dir \
        brainglobe-atlasapi \
        brainglobe-space \
        brainglobe-utils \
        brainreg \
    && /opt/conda/bin/conda clean -afy

# Verify the BrainGlobe stack imports correctly
RUN /opt/conda/envs/brainglobe/bin/python -c \
    "import brainglobe_atlasapi, brainglobe_space, brainglobe_utils, brainreg; \
     from brainglobe_atlasapi.list_atlases import get_all_atlases_lastversions; \
     print('[OK] BrainGlobe stack:', brainglobe_atlasapi.__version__, \
           len(get_all_atlases_lastversions()), 'atlases available')"

# Atlases (hundreds of MB each) download on first use to brainglobe's default
# $HOME/.brainglobe (config in $HOME/.config/brainglobe). $HOME is the
# imagentj_home named volume, so they persist across restarts without being
# baked into the image. No env var needed — the defaults already land there.

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
COPY --chmod=755 micromamba_shim.sh /usr/local/opt/micromamba/bin/micromamba
RUN ln -sf micromamba /usr/local/opt/micromamba/bin/conda \
    && mkdir -p /opt/micromamba/bin \
    && cp /usr/local/opt/micromamba/bin/micromamba /opt/micromamba/bin/micromamba \
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

# ── Runtime config baked into the image ──────────────────────────────────────
# imagentj_config.yaml (LLM-per-role + Vision/QA switches) is already included
# by `COPY . /app` above; this explicit copy documents the contract and keeps
# the file present even if the build context is trimmed. docker-compose.yml
# bind-mounts the host copy over this one, so host edits still win at runtime
# without a rebuild; a bare `docker run` (no mount) falls back to this baked default.
COPY imagentj_config.yaml /app/imagentj_config.yaml

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
# Download the model bundle from the project's cloud storage and extract it
# directly into the cellpose models directory so a pulled image works offline.
# The imagentj_home named volume seeds from /home/imagentj.seed (created below),
# so models are available on first container start without any host files.
RUN mkdir -p /home/imagentj/.cellpose/models \
    && echo "[cellpose] Downloading model bundle..." \
    && curl -fsSL "https://owncloud.ut.ee/owncloud/s/HyXebMNEPd7niMa/download" -o /tmp/models.zip \
    && echo "[cellpose] Extracting models..." \
    && unzip -q /tmp/models.zip -d /tmp/models_extracted \
    && cp -a /tmp/models_extracted/models/. /home/imagentj/.cellpose/models/ \
    && rm -rf /tmp/models.zip /tmp/models_extracted \
    && echo "[cellpose] Baked in $(ls /home/imagentj/.cellpose/models | wc -l) model files" \
    && chown -R imagentj:imagentj /home/imagentj/.cellpose

# ── Seed home dir for named-volume persistence ────────────────────────────────
# imagentj_home is a named volume mounted at /home/imagentj. It starts empty,
# shadowing these baked-in config files. The entrypoint seeds it on first start.
RUN cp -a /home/imagentj /home/imagentj.seed

# ── Environment defaults ─────────────────────────────────────────────────────
ENV DISPLAY=:1
ENV QT_QPA_PLATFORM=xcb
ENV JAVA_HOME=/opt/conda/envs/local_imagent_J/lib/jvm
ENV HOME=/home/imagentj

# ── noVNC: default scaling mode → Local Scaling ──────────────────────────────
# noVNC stores the resize/scaling preference in the browser's localStorage.
# Patching the default in ui.js sets it for every fresh browser session without
# the user needing to open the settings panel.
RUN NOVNC_UI=/usr/share/novnc/app/ui.js; \
    if [ -f "$NOVNC_UI" ]; then \
        sed -i "s/initSetting('resize', 'off')/initSetting('resize', 'scale')/g" "$NOVNC_UI" \
        && echo "[novnc] Default scaling mode set to 'scale' (Local Scaling)"; \
    else \
        echo "[novnc] WARNING: ui.js not found at $NOVNC_UI — scaling default not patched"; \
    fi

COPY --chmod=755 docker-entrypoint.sh /docker-entrypoint.sh

# ── Pre-warm jgo/Maven dependency cache ──────────────────────────────────────
# pyimagej resolves imglib2-imglyb and other bridge JARs via jgo/Maven at
# first startup. maven.scijava.org is frequently unreliable so we resolve
# everything during the build (when network is available) and store the result
# in /opt/imagentj-seed/. The entrypoint seeds ~/.jgo and ~/.m2 from there
# on first container start, before the imagentj_home volume can shadow them.
COPY bundled_cache/imagentj-seed-cache.tar.gz /tmp/imagentj-seed-cache.tar.gz
RUN mkdir -p /opt/imagentj-seed \
    && tar xzf /tmp/imagentj-seed-cache.tar.gz -C /opt/imagentj-seed \
    && rm /tmp/imagentj-seed-cache.tar.gz \
    && chmod -R a+rX /opt/imagentj-seed \
    && echo "[pre-warm] jgo/Maven cache extracted to /opt/imagentj-seed"

EXPOSE 6080

USER imagentj

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "gui_runner.py"]
