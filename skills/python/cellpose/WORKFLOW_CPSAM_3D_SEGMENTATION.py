# imagentj-env: cellpose4
"""
Cellpose-SAM (cpsam) 3D segmentation — one or more z-stacks, one loaded model.
==============================================================================
Copy this and edit the CONFIG block. Do not rewrite it from scratch. It is the
3D twin of WORKFLOW_CPSAM_BATCH_SEGMENTATION.py (which is for 2D images).

Input: a folder of z-stacks (TIFF / OME-TIFF), one time point each, single- or
multi-channel. Output per stack:
  <stem><suffix>.tif            3D instance-label stack (0 = background), saved as an
                                ImageJ hyperstack WITH the voxel calibration, so Fiji /
                                3D ImageJ Suite / MorphoLibJ measure it in physical units
  <stem><suffix>_objects.csv    one row per object: volume (voxels and unit^3), centroid,
                                z-extent, border flags
  <stem><suffix>_QC.png         orthogonal views (XY | YZ / XZ) with label overlay, z drawn
                                at true scale — LOOK AT IT before trusting the numbers
plus cpsam_3d_summary.csv over all stacks.

WHY THE SETTINGS BELOW ARE WHAT THEY ARE (all measured on this install, cellpose 4.1.1):

  * MODE "3d" (do_3D=True) is the default and the one to use. It runs the network on
    the XY, ZY and ZX planes and integrates a true 3D flow field. Stitching 2D masks
    through z ("stitch") was worse in every controlled test (F1@0.5 0.70-0.90 vs
    0.92-1.00) and fragments objects into single-plane pieces. Use "stitch" only when
    objects are thinner than ~3 planes or 3D is too slow for a huge volume.

  * ANISOTROPY = z-step / xy pixel size, read from the file calibration. It MUST be
    right. cpsam upsamples z by this factor so the ZY/ZX views look isotropic.

  * resample=False IS REQUIRED WITH ANISOTROPY. With the default resample=True,
    cellpose shrinks the flow field back to the coarse z grid by interpolation but does
    NOT rescale the z component, so voxels overshoot in z during the flow dynamics and
    objects split or merge. Measured: nuclei F1@0.5 fell 1.00 -> 0.84 -> 0.51 -> 0.32
    as the z-step grew 1x -> 2x -> 3x -> 4x; with resample=False it stayed 1.00 at
    every step. This script runs the dynamics on the upsampled grid and maps the labels
    back to the original planes itself. Do not "simplify" that away.

  * flow_threshold DOES NOTHING IN 3D — cellpose skips its flow-error QC when
    do_3D=True. The cleanup knobs are cellprob_threshold and MIN_VOLUME.

  * MIN_VOLUME "auto": cellpose's own min_size=15 voxels is a 2D-sized default. Real 3D
    output has a bimodal size distribution: genuine objects plus small debris
    fragments (caps along a bright membrane layer, specks). "auto" removes objects
    smaller than 10% of the volume-weighted median object volume (the size of the
    object a typical labelled voxel belongs to, which debris cannot drag down). The
    count removed is printed and written to the summary — never silent.

  * NO DIAMETER: cpsam handled objects from ~25 to ~70 px across without one. In 3D a
    diameter rescales X, Y AND Z, so only set it with a reason (EVAL_KWARGS).

  * CHANNELS: cpsam accepts up to 3 channels together. For whole cells give the
    boundary/cytoplasm channel first and the nuclear channel second, e.g. [1, 0];
    for nuclei give just the nuclear channel. A stack with one channel needs None.

MEMORY / TIME: one stack is processed at a time. With anisotropy a, GPU work scales
with Z*a*Y*X. Measured on one A100: 60x256x256 (a=1.1) ~25 s; 84x1000x1000 (a=3.1)
9.5 min and 13.7 GB peak RAM — about 55 bytes per voxel of the z-upsampled stack (flows +
masks). The script checks this against the free RAM (cgroup-aware) BEFORE loading the
model and stops with VERIFICATION FAILED if a stack will not fit — an out-of-memory kill
gives no Python error and can take the agent container down (12 GB limit by default).
"""

import csv
import glob
import json
import os
import time
import xml.etree.ElementTree as ET

import numpy as np
import tifffile
from cellpose import models

# ── CONFIG (edit these) ──────────────────────────────────────────────────────
INPUT_DIR = "/app/data/.../stacks"
OUTPUT_DIR = "/app/data/.../cpsam_3d_out"
PATTERN = "*.tif"

# None for a single-channel stack. Otherwise a list of up to 3 channel indices fed to
# cpsam together, e.g. [1, 0] = boundary/cytoplasm channel 1 + nuclear channel 0.
CHANNELS = None
SUFFIX = "_labels"          # output name: <stem><SUFFIX>.tif

# (z, y, x) voxel size in the file's unit. None = read from the file calibration.
# Set it explicitly ONLY when the file has no calibration and the user told you the
# voxel size — never guess. Only the z/xy ratio drives segmentation; the absolute
# values give the physical volumes in the CSV.
VOXEL_SIZE_ZYX = None
VOXEL_UNIT = "um"           # used only together with VOXEL_SIZE_ZYX

MODE = "3d"                 # "3d" (default, recommended) or "stitch"
STITCH_THRESHOLD = 0.25     # MODE="stitch" only: IoU needed to link masks across planes

MIN_VOLUME = "auto"         # "auto", an int number of voxels, or 0 to keep everything

# Passed to eval(). cellprob_threshold: lower (-1, -2) if dim objects are missed,
# raise (1, 2) if background is labelled. batch_size 32 is ~20% faster than 8 on an A100.
EVAL_KWARGS = dict(cellprob_threshold=0.0, batch_size=32)

USE_GPU = True              # cpsam in 3D on CPU takes hours — keep this True
WRITE_QC_PNG = True
# ─────────────────────────────────────────────────────────────────────────────

UNIT_ALIASES = {"um": "um", "µm": "um", "\\u00B5m": "um", "micron": "um", "microns": "um",
                "micrometer": "um", "nm": "nm", "nanometer": "nm", "mm": "mm", "millimeter": "mm"}


# ── reading ─────────────────────────────────────────────────────────────────
def read_stack(path):
    """Return (array, axes string) with axes from the file, e.g. 'ZCYX'."""
    with tifffile.TiffFile(path) as tf:
        s = tf.series[0]
        arr = s.asarray()
        axes = s.axes
    # tifffile labels an un-annotated leading axis Q/I; with 3 dims that is the z axis.
    if arr.ndim == 3 and axes[0] in "QI" and "Z" not in axes:
        print(f"  NOTE: {os.path.basename(path)} has no axis metadata; treating the first "
              f"axis ({arr.shape[0]}) as Z.", flush=True)
        axes = "Z" + axes[1:]
    return arr, axes


def read_voxel_size(path):
    """(z, y, x, unit) from ImageJ or OME metadata, or None if not calibrated."""
    with tifffile.TiffFile(path) as tf:
        if tf.is_ome and tf.ome_metadata:
            try:
                root = ET.fromstring(tf.ome_metadata)
                px = root.find(".//{*}Pixels")
                vals = [px.get(f"PhysicalSize{a}") for a in "ZYX"]
                unit = px.get("PhysicalSizeXUnit", "µm")
                if all(vals) and UNIT_ALIASES.get(unit):
                    z, y, x = (float(v) for v in vals)
                    return z, y, x, UNIT_ALIASES[unit]
            except ET.ParseError:
                pass
        ij = tf.imagej_metadata or {}
        page = tf.pages[0]
        unit = UNIT_ALIASES.get(str(ij.get("unit", "")).strip().lower())
        xr, yr = page.tags.get("XResolution"), page.tags.get("YResolution")
        z = ij.get("spacing")
        if unit is None or xr is None or yr is None or z is None:
            return None
        xn, xd = xr.value; yn, yd = yr.value
        if xn == 0 or yn == 0:
            return None
        x, y = xd / xn, yd / yn
        # 1 px = 1 unit is ImageJ's "no calibration" default, and 72-dpi inch defaults
        # never carry a micron unit, so neither passes the unit check above.
        if x == 1.0 and y == 1.0 and float(z) == 1.0:
            return None
        return float(z), y, x, unit


def to_zyxc(arr, axes, channels, name):
    """Reorder to Z,Y,X,C (C only if channels is a list)."""
    axes = axes.replace("S", "C")
    for a in axes:
        if a not in "ZCYX" and arr.shape[axes.index(a)] != 1:
            raise SystemExit(f"VERIFICATION FAILED: {name}: axis '{a}' has size "
                             f"{arr.shape[axes.index(a)]} (axes {axes}, shape {arr.shape}). "
                             "Give one time point / one position per file.")
    keep = [i for i, a in enumerate(axes) if a in "ZCYX"]
    arr = arr.reshape([arr.shape[i] for i in keep]) if len(keep) < arr.ndim else arr
    axes = "".join(axes[i] for i in keep)
    if "Z" not in axes or arr.shape[axes.index("Z")] < 3:
        raise SystemExit(f"VERIFICATION FAILED: {name}: no z axis with >= 3 planes "
                         f"(axes {axes}, shape {arr.shape}). This workflow is for z-stacks; "
                         "use WORKFLOW_CPSAM_BATCH_SEGMENTATION.py for 2D images.")
    if "C" in axes:
        if channels is None:
            raise SystemExit(f"VERIFICATION FAILED: {name} has {arr.shape[axes.index('C')]} "
                             "channels; set CHANNELS to the channel index list to segment.")
        nc = arr.shape[axes.index("C")]
        bad = [c for c in channels if not 0 <= c < nc]
        if bad:
            raise SystemExit(f"VERIFICATION FAILED: {name}: CHANNELS {bad} out of range "
                             f"(file has {nc} channels).")
        arr = np.moveaxis(arr, [axes.index(a) for a in "ZYXC"], [0, 1, 2, 3])
        return arr[..., list(channels)]
    if channels not in (None, [0], (0,)):
        raise SystemExit(f"VERIFICATION FAILED: {name} is single-channel but CHANNELS="
                         f"{channels}. Set CHANNELS = None.")
    return np.moveaxis(arr, [axes.index(a) for a in "ZYX"], [0, 1, 2])


def available_memory_bytes():
    """Free RAM for this process: min(host MemAvailable, cgroup limit - cgroup usage)."""
    avail = None
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                avail = int(line.split()[1]) * 1024
    except OSError:
        pass
    for lim_p, use_p in (("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
                         ("/sys/fs/cgroup/memory/memory.limit_in_bytes",
                          "/sys/fs/cgroup/memory/memory.usage_in_bytes")):
        try:
            lim = open(lim_p).read().strip()
            if lim != "max" and int(lim) < 1 << 60:
                free = int(lim) - int(open(use_p).read().strip())
                avail = free if avail is None else min(avail, free)
            break
        except (OSError, ValueError):
            continue
    return avail


# ── label utilities ─────────────────────────────────────────────────────────
def relabel_sequential(lab):
    ids = np.unique(lab)
    ids = ids[ids > 0]
    lut = np.zeros(int(lab.max()) + 1, np.uint32)
    lut[ids] = np.arange(1, ids.size + 1, dtype=np.uint32)
    return lut[lab]


def auto_min_volume(lab):
    v = np.bincount(lab.ravel())
    v = v[1:][v[1:] > 0]
    if v.size == 0:
        return 0
    v = np.sort(v)
    cum = np.cumsum(v)
    weighted_median = v[np.searchsorted(cum, cum[-1] / 2)]
    return int(0.1 * weighted_median)


def per_object_table(lab, vz, vy, vx):
    """Volumes, centroids, z-extent and border flags, one plane at a time (low RAM)."""
    n = int(lab.max())
    Z, Y, X = lab.shape
    vol = np.zeros(n + 1); sz = np.zeros(n + 1); sy = np.zeros(n + 1); sx = np.zeros(n + 1)
    zmin = np.full(n + 1, Z); zmax = np.full(n + 1, -1)
    xy_border = np.zeros(n + 1, bool); z_border = np.zeros(n + 1, bool)
    yy, xx = np.mgrid[0:Y, 0:X]
    for z in range(Z):
        p = lab[z].ravel()
        c = np.bincount(p, minlength=n + 1)
        vol += c; sz += c * z
        sy += np.bincount(p, weights=yy.ravel(), minlength=n + 1)
        sx += np.bincount(p, weights=xx.ravel(), minlength=n + 1)
        present = c > 0
        zmin[present] = np.minimum(zmin[present], z); zmax[present] = np.maximum(zmax[present], z)
        edge = np.concatenate([lab[z, 0], lab[z, -1], lab[z, :, 0], lab[z, :, -1]])
        xy_border[np.unique(edge)] = True
        if z in (0, Z - 1):
            z_border[np.unique(lab[z])] = True
    rows = []
    for i in range(1, n + 1):
        if vol[i] == 0:
            continue
        cz, cy, cx = sz[i] / vol[i], sy[i] / vol[i], sx[i] / vol[i]
        rows.append(dict(label=i, volume_voxels=int(vol[i]),
                         volume_unit3=round(vol[i] * vz * vy * vx, 4),
                         centroid_z_px=round(cz, 2), centroid_y_px=round(cy, 2), centroid_x_px=round(cx, 2),
                         centroid_z_unit=round(cz * vz, 4), centroid_y_unit=round(cy * vy, 4),
                         centroid_x_unit=round(cx * vx, 4),
                         z_planes=int(zmax[i] - zmin[i] + 1),
                         touches_xy_border=bool(xy_border[i]), touches_z_border=bool(z_border[i])))
    return rows


# ── QC rendering ────────────────────────────────────────────────────────────
def write_qc_png(img_zyx, lab, anisotropy, path):
    import cv2

    def norm8(a):
        a = a.astype(np.float32)
        lo, hi = np.percentile(a, [1, 99.8])
        return (np.clip((a - lo) / (hi - lo + 1e-9), 0, 1) * 255).astype(np.uint8)

    lut = np.random.default_rng(0).integers(60, 256, size=(int(lab.max()) + 1, 3), dtype=np.uint8)
    lut[0] = 0

    def overlay(g, l):
        rgb = np.dstack([g] * 3).astype(np.float32)
        col = lut[l].astype(np.float32)
        fg = l > 0
        rgb[fg] = 0.6 * rgb[fg] + 0.4 * col[fg]
        e = np.zeros_like(fg)
        e[:-1] |= l[:-1] != l[1:]; e[1:] |= l[:-1] != l[1:]
        e[:, :-1] |= l[:, :-1] != l[:, 1:]; e[:, 1:] |= l[:, :-1] != l[:, 1:]
        e &= fg
        rgb[e] = col[e]
        return rgb.astype(np.uint8)

    Z, Y, X = lab.shape
    fg_per_z = (lab > 0).reshape(Z, -1).sum(1)
    z0 = int(np.argmax(fg_per_z)) if fg_per_z.any() else Z // 2
    g = norm8(img_zyx)
    zh = max(1, int(round(Z * anisotropy)))
    xy = overlay(g[z0], lab[z0])
    xz = cv2.resize(overlay(g[:, Y // 2], lab[:, Y // 2]), (X, zh), interpolation=cv2.INTER_NEAREST)
    yz = cv2.resize(overlay(g[:, :, X // 2], lab[:, :, X // 2]), (Y, zh), interpolation=cv2.INTER_NEAREST)
    yz = np.ascontiguousarray(np.transpose(yz, (1, 0, 2)))
    canvas = np.full((Y + zh + 6, X + zh + 6, 3), 40, np.uint8)
    canvas[:Y, :X] = xy; canvas[Y + 6:, :X] = xz; canvas[:Y, X + 6:] = yz
    # crosshair ticks showing where the side views cut
    canvas[Y // 2, :X][::4] = 255; canvas[:Y, X // 2][::4] = 255
    scale = min(1.0, 1600 / max(canvas.shape[:2]))
    if scale < 1:
        canvas = cv2.resize(canvas, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    fs = float(np.clip(canvas.shape[1] / 1100, 0.3, 0.6))
    band = np.full((int(32 * fs / 0.6) + 6, canvas.shape[1], 3), 0, np.uint8)
    cv2.putText(band, f"XY z={z0} | right: YZ x={X // 2} | bottom: XZ y={Y // 2} | z at true scale",
                (4, band.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), 1, cv2.LINE_AA)
    canvas = np.vstack([band, canvas])
    cv2.imwrite(path, canvas[..., ::-1])


# ── main ────────────────────────────────────────────────────────────────────
files = sorted(glob.glob(os.path.join(INPUT_DIR, PATTERN)))
if not files:
    raise SystemExit(f"VERIFICATION FAILED: no files matching {PATTERN} in {INPUT_DIR}")
if MODE not in ("3d", "stitch"):
    raise SystemExit(f"VERIFICATION FAILED: MODE must be '3d' or 'stitch', not {MODE!r}")
if "flow_threshold" in EVAL_KWARGS and MODE == "3d":
    print("NOTE: flow_threshold has no effect in 3D mode (cellpose skips that QC); "
          "use cellprob_threshold / MIN_VOLUME instead.", flush=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"Found {len(files)} stack(s) in {INPUT_DIR}", flush=True)

# Check every file's calibration BEFORE loading the model, so a missing voxel size
# fails in seconds rather than after the first stack has run.
calib = {}
for f in files:
    if VOXEL_SIZE_ZYX is not None:
        calib[f] = (*map(float, VOXEL_SIZE_ZYX), VOXEL_UNIT)
        continue
    c = read_voxel_size(f)
    if c is None:
        raise SystemExit(
            f"VERIFICATION FAILED: {os.path.basename(f)} has no usable voxel calibration "
            "(need the xy pixel size AND the z-step in um/nm/mm). The z/xy ratio decides how "
            "cpsam reshapes the stack, so it cannot be guessed. Ask the user for the voxel "
            "size and set VOXEL_SIZE_ZYX = (z, y, x).")
    calib[f] = c

# Memory pre-flight, also before the model loads. 3D cpsam holds flows and labels for the
# z-UPSAMPLED stack in RAM (~55 bytes per upsampled voxel + ~2 GB for the model). Running
# out does not raise a Python error — the kernel OOM-kills the process, and inside the agent
# container that can take the whole container down. So refuse up front instead.
avail = available_memory_bytes()
for f in files:
    with tifffile.TiffFile(f) as tf:
        shp, axs = tf.series[0].shape, tf.series[0].axes
    dims = {a: n for a, n in zip(axs.replace("Q", "Z").replace("I", "Z"), shp)}
    Z, Y, X = dims.get("Z", 1), dims.get("Y", 1), dims.get("X", 1)
    vz, vy, vx, _ = calib[f]
    zfac = vz / ((vy + vx) / 2) if MODE == "3d" else 1.0
    need = Z * max(zfac, 1.0) * Y * X * 55 + 2e9
    if avail and need > 0.9 * avail:
        raise SystemExit(
            f"VERIFICATION FAILED: {os.path.basename(f)} ({Z}x{Y}x{X}, anisotropy {zfac:.1f}) "
            f"needs ~{need / 1e9:.1f} GB RAM for 3D segmentation but only ~{avail / 1e9:.1f} GB "
            "is available. Crop it to the region of interest or split it into XY blocks (each "
            "block then segments separately — objects on block borders get cut), or ask the "
            "user to raise the container memory limit. Do NOT fall back to plane-by-plane 2D.")

model = models.CellposeModel(gpu=USE_GPU)   # ONCE — cpsam is the default weight
print(f"cpsam loaded once; mode={MODE}", flush=True)

summary = []
for f in files:
    stem = os.path.splitext(os.path.basename(f))[0]
    if stem.endswith(".ome"):
        stem = stem[:-4]
    vz, vy, vx, unit = calib[f]
    anisotropy = vz / ((vy + vx) / 2)
    if abs(vy - vx) / max(vy, vx) > 0.02:
        print(f"  WARNING: {stem}: non-square pixels ({vy} x {vx}); using their mean.", flush=True)

    arr, axes = read_stack(f)
    x = to_zyxc(arr, axes, CHANNELS, stem)
    del arr
    Z = x.shape[0]
    print(f"[{stem}] shape ZYX{'C' if x.ndim == 4 else ''}={x.shape}, voxel "
          f"{vz:g} x {vy:g} x {vx:g} {unit}, anisotropy={anisotropy:.2f}", flush=True)
    if anisotropy > 6:
        print(f"  WARNING: anisotropy {anisotropy:.1f} — z is very coarse; objects only a few "
              "planes thick may segment poorly in either mode. Check the QC PNG.", flush=True)

    kw = dict(z_axis=0, **EVAL_KWARGS)
    if x.ndim == 4:
        kw["channel_axis"] = 3
    if MODE == "3d":
        kw.update(do_3D=True, anisotropy=anisotropy, resample=False)
    else:
        kw.update(stitch_threshold=STITCH_THRESHOLD)

    t0 = time.time()
    masks = model.eval(x, **kw)[0]
    seconds = time.time() - t0
    masks = np.asarray(masks)

    # resample=False returns the labels on the z-upsampled grid; take, for every
    # original plane, the upsampled plane at the same physical position (cv2's
    # pixel-centre convention, which is what cellpose used to upsample).
    if masks.shape[0] != Z:
        zf = masks.shape[0] / Z
        zi = np.clip(np.round((np.arange(Z) + 0.5) * zf - 0.5).astype(int), 0, masks.shape[0] - 1)
        masks = masks[zi]
    masks = relabel_sequential(masks.astype(np.uint32))
    n_raw = int(masks.max())

    min_vol = auto_min_volume(masks) if MIN_VOLUME == "auto" else int(MIN_VOLUME)
    removed = 0
    if min_vol > 0 and n_raw:
        v = np.bincount(masks.ravel())
        small = np.nonzero((v < min_vol) & (np.arange(v.size) > 0))[0]
        removed = int(small.size)
        if removed:
            lut = np.arange(v.size, dtype=np.uint32); lut[small] = 0
            masks = relabel_sequential(lut[masks])
    n = int(masks.max())

    # Save: uint16 ImageJ hyperstack with calibration when it fits, else uint32 TIFF.
    out_tif = os.path.join(OUTPUT_DIR, f"{stem}{SUFFIX}.tif")
    if n <= 65535:
        tifffile.imwrite(out_tif, masks.astype(np.uint16), imagej=True,
                         resolution=(1 / vx, 1 / vy),
                         metadata={"spacing": vz, "unit": "micron" if unit == "um" else unit,
                                   "axes": "ZYX"})
    else:
        print(f"  WARNING: {n} objects > 65535 — writing uint32, which ImageJ cannot open as "
              "labels. Split the volume to use it in Fiji.", flush=True)
        tifffile.imwrite(out_tif, masks)

    rows = per_object_table(masks, vz, vy, vx)
    obj_csv = os.path.join(OUTPUT_DIR, f"{stem}{SUFFIX}_objects.csv")
    with open(obj_csv, "w", newline="") as fh:
        fields = ["label", "volume_voxels", "volume_unit3", "centroid_z_px", "centroid_y_px",
                  "centroid_x_px", "centroid_z_unit", "centroid_y_unit", "centroid_x_unit",
                  "z_planes", "touches_xy_border", "touches_z_border"]
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)

    if WRITE_QC_PNG:
        qc_img = x if x.ndim == 3 else x[..., 0]
        write_qc_png(qc_img, masks, anisotropy, os.path.join(OUTPUT_DIR, f"{stem}{SUFFIX}_QC.png"))

    zpl = np.array([r["z_planes"] for r in rows]) if rows else np.array([0])
    vols = np.array([r["volume_unit3"] for r in rows]) if rows else np.array([0.0])
    s = dict(image_stem=stem, mode=MODE, anisotropy=round(anisotropy, 3), unit=unit,
             objects=n, removed_small=removed, min_volume_voxels=min_vol,
             median_volume_unit3=round(float(np.median(vols)), 3),
             median_z_planes=float(np.median(zpl)),
             frac_single_plane=round(float((zpl == 1).mean()), 3) if rows else 0.0,
             frac_touching_border=round(float(np.mean([r["touches_xy_border"] or r["touches_z_border"]
                                                        for r in rows])), 3) if rows else 0.0,
             seconds=round(seconds, 1), label_path=out_tif)
    summary.append(s)
    print(f"[{stem}] {n} objects ({removed} fragments < {min_vol} voxels removed), median "
          f"volume {s['median_volume_unit3']} {unit}^3, median z-extent {s['median_z_planes']:g} "
          f"planes, {seconds:.0f} s", flush=True)

    # ── per-stack plausibility checks ──
    if n == 0:
        print(f"  WARNING: {stem}: 0 objects. Wrong channel, blank stack, or objects darker "
              "than background (cpsam expects bright objects).", flush=True)
    elif s["frac_single_plane"] > 0.2 and Z > 3:
        print(f"  WARNING: {stem}: {s['frac_single_plane']:.0%} of objects occupy a single "
              "plane — fragmentation. In 'stitch' mode switch to '3d'; in '3d' check the "
              "voxel calibration.", flush=True)
    if n and s["median_z_planes"] >= 0.9 * Z and Z > 5:
        print(f"  WARNING: {stem}: the typical object spans the whole stack in z — wrong axis "
              "order or wrong z calibration? Check the QC PNG.", flush=True)
    del x, masks

sum_csv = os.path.join(OUTPUT_DIR, "cpsam_3d_summary.csv")
with open(sum_csv, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(summary[0].keys())); w.writeheader(); w.writerows(summary)
with open(os.path.join(OUTPUT_DIR, "cpsam_3d_settings.json"), "w") as fh:
    json.dump(dict(mode=MODE, channels=CHANNELS, min_volume=MIN_VOLUME, eval_kwargs=EVAL_KWARGS,
                   stitch_threshold=STITCH_THRESHOLD if MODE == "stitch" else None,
                   voxel_size_override=VOXEL_SIZE_ZYX, cellpose_model="cpsam"), fh, indent=1)

if len(summary) != len(files):
    raise SystemExit(f"VERIFICATION FAILED: {len(summary)} results for {len(files)} stacks")
if all(s["objects"] == 0 for s in summary):
    raise SystemExit("VERIFICATION FAILED: 0 objects in EVERY stack. Check CHANNELS and that "
                     "the stacks contain bright objects.")
print(f"Wrote {len(summary)} label stack(s), per-object CSVs and {sum_csv}")
