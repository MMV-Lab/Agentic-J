# imagentj-env: cellpose4
"""
Cellpose-SAM (cpsam) batch segmentation — a FOLDER of images, one loaded model.
==============================================================================
Copy this and edit the CONFIG block. Do not rewrite it from scratch, and do not
construct the model inside the loop.

This is the CPSAM twin of WORKFLOW_BATCH_SEGMENTATION.py. Use THIS one when the
model is cpsam; use that one for the v3 models (cyto3, nuclei, tissuenet_cp3, ...).
They cannot be merged: cpsam lives in the `cellpose4` env and the two APIs differ.

WHY A SEPARATE SCRIPT — the v4 API is not the v3 API:
  * `models.Cellpose` DOES NOT EXIST in cellpose 4. Only `models.CellposeModel`.
  * cpsam is the default weight, so no model name is needed. `model_type=` is
    accepted but silently ignored (it only warns).
  * `eval()` returns THREE values (masks, flows, styles) — no `diams`.
  * NO DIAMETER and NO CHANNELS are needed: cpsam is channel-agnostic and does its
    own sizing. See DIAMETER below before you reach for one anyway.
  * The header above MUST say cellpose4. In the `cellpose` env this script fails
    with ModuleNotFoundError / AttributeError.

DIAMETER: leave it out. The default behaves like diameter=30, and passing a
different value DOES change the segmentation — it is not ignored. Only set one if
you have a specific reason, in which case put it in EVAL_KWARGS below.

eval() accepts a LIST of images and batches internally, exactly like the v3 route,
so the model is loaded once and every image reuses it.

OUTPUT: one uint16 instance-label TIF per input (0 = background, 1..N = objects),
named <stem><suffix>.tif, plus a summary CSV of per-image object counts.

MEMORY: masks for a chunk are held in RAM before writing. Lower CHUNK for large
images or a very big folder.
"""

import csv
import glob
import os

import numpy as np
import tifffile
from cellpose import models

# ── CONFIG (edit these) ──────────────────────────────────────────────────────
INPUT_DIR = "/app/data/.../input"
OUTPUT_DIR = "/app/data/.../cpsam_out"
PATTERN = "*.tif"           # e.g. "*.tiff", "*.png"
CHUNK = 100                 # images per eval() call; lower if RAM-constrained

# One entry per compartment. cpsam needs no model name and no diameter, so a pass
# is just "which plane, and where do the masks go".
#   channel: index into the LAST axis for a multi-channel image (RGB: 0=R, 1=G, 2=B),
#            or None for an already-2D single-channel image.
PASSES = [
    dict(name="cells", channel=0, out_subdir="cell_masks", suffix="_cells"),
    # dict(name="nuclei", channel=2, out_subdir="nuclei_masks", suffix="_nuclei"),
]

# Passed straight to eval(). Add flow_threshold / cellprob_threshold to tune, and
# `diameter` ONLY if you truly want to override cpsam's own sizing (see above).
EVAL_KWARGS = dict(flow_threshold=0.4, cellprob_threshold=0.0)

USE_GPU = True              # cpsam is very slow on CPU — keep this True
# ─────────────────────────────────────────────────────────────────────────────


def load_channel(path, channel):
    """Read one image and return the 2D plane to segment."""
    arr = tifffile.imread(path)
    if channel is None:
        if arr.ndim != 2:
            raise ValueError(
                f"{os.path.basename(path)}: expected 2D but got shape {arr.shape}. "
                "Set 'channel' in the pass config to pick a plane.")
        return arr
    if arr.ndim != 3:
        raise ValueError(
            f"{os.path.basename(path)}: channel={channel} requested but array is "
            f"{arr.ndim}D with shape {arr.shape}.")
    # Channels are usually last (H, W, C) but can be first (C, H, W) — pick the
    # smaller axis as the channel axis rather than assuming.
    if arr.shape[-1] <= arr.shape[0]:
        return arr[..., channel]
    return arr[channel]


files = sorted(glob.glob(os.path.join(INPUT_DIR, PATTERN)))
if not files:
    raise SystemExit(f"VERIFICATION FAILED: no files matching {PATTERN} in {INPUT_DIR}")
stems = [os.path.splitext(os.path.basename(f))[0] for f in files]
print(f"Found {len(files)} images in {INPUT_DIR}", flush=True)

os.makedirs(OUTPUT_DIR, exist_ok=True)
rows = []

# THE POINT OF THIS SCRIPT: one construction, reused for every image below.
# cpsam is the default pretrained_model, so no name is passed.
model = models.CellposeModel(gpu=USE_GPU)
print(f"cpsam model loaded once (CellposeModel); {len(PASSES)} pass(es) over "
      f"{len(files)} images", flush=True)

for cfg in PASSES:
    out_dir = os.path.join(OUTPUT_DIR, cfg["out_subdir"])
    os.makedirs(out_dir, exist_ok=True)

    written = 0
    for start in range(0, len(files), CHUNK):
        batch_files = files[start:start + CHUNK]
        planes = [load_channel(p, cfg["channel"]) for p in batch_files]
        # v4 eval returns 3 values, not 4 — masks is first either way, so index.
        masks = model.eval(planes, **EVAL_KWARGS)[0]
        if len(masks) != len(batch_files):
            raise SystemExit(
                f"VERIFICATION FAILED: cpsam returned {len(masks)} masks for "
                f"{len(batch_files)} images")
        for k, m in enumerate(masks):
            stem = stems[start + k]
            # uint16 keeps up to 65535 objects; uint8 would silently truncate at 255.
            m16 = np.asarray(m).astype(np.uint16)
            path = os.path.join(out_dir, f"{stem}{cfg['suffix']}.tif")
            tifffile.imwrite(path, m16)
            rows.append({"image_stem": stem, "pass": cfg["name"],
                         "objects": int(m16.max()), "mask_path": path})
            written += 1
        print(f"[{cfg['name']}] {written}/{len(files)} written", flush=True)

summary = os.path.join(OUTPUT_DIR, "cpsam_batch_summary.csv")
with open(summary, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["image_stem", "pass", "objects", "mask_path"])
    w.writeheader()
    w.writerows(rows)

# Fail loudly rather than reporting success on a partial run.
expected = len(files) * len(PASSES)
if len(rows) != expected:
    raise SystemExit(
        f"VERIFICATION FAILED: wrote {len(rows)} masks, expected {expected}")

for cfg in PASSES:
    counts = [r["objects"] for r in rows if r["pass"] == cfg["name"]]
    empty = [r["image_stem"] for r in rows
             if r["pass"] == cfg["name"] and r["objects"] == 0]
    print(f"[{cfg['name']}] objects per image: min={min(counts)} "
          f"median={int(np.median(counts))} max={max(counts)}")

    # A mask file exists for every input even when cpsam found nothing, so the
    # count check above passes on a totally failed pass. Zero objects everywhere
    # means the config is wrong (wrong channel, blank plane) — a failure, not a result.
    if len(empty) == len(files):
        raise SystemExit(
            f"VERIFICATION FAILED: pass '{cfg['name']}' found 0 objects in ALL "
            f"{len(files)} images. Check channel={cfg['channel']} and that the "
            f"plane actually contains signal.")

    # A few empties can be genuine (a faint or blank field), so warn rather than
    # fail — but never let them reach the summary table unannounced.
    if empty:
        print(f"[{cfg['name']}] WARNING: 0 objects in {len(empty)}/{len(files)} "
              f"images: {', '.join(empty)}")

print(f"Wrote {len(rows)} masks and {summary}")
