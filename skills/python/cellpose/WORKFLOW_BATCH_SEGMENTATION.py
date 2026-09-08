# imagentj-env: cellpose
"""
Cellpose batch segmentation — a FOLDER of images, one loaded model.
===================================================================
Copy this and edit the CONFIG block. Do not rewrite it from scratch, and do not
construct the model inside the loop.

THE ONE RULE: build `models.Cellpose(...)` ONCE, outside the loop. Every
construction reloads the weights; doing it per image is the single most common
way these scripts get slow.

eval() accepts a LIST of images and batches internally, which is what this uses.
The gain over a per-image loop is small once the model is resident; the big win is
loading the model once. If your images differ in size, eval(list) still works —
unlike the Fiji T-stack route, which requires uniform dimensions.

OUTPUT: one uint16 instance-label TIF per input (0 = background, 1..N = objects),
named <stem><suffix>.tif, plus a summary CSV of per-image object counts.

MEMORY: masks for the whole folder are held in RAM before writing — small for
typical 2D fields, but for large images or a very big folder lower CHUNK so eval()
is called on slices of the list.
"""

import csv
import glob
import os

import numpy as np
import tifffile
from cellpose import models

# ── CONFIG (edit these) ──────────────────────────────────────────────────────
INPUT_DIR = "/app/data/.../input"
OUTPUT_DIR = "/app/data/.../cellpose_out"
PATTERN = "*.tif"           # e.g. "*.tiff", "*.png"
CHUNK = 200                 # images per eval() call; lower if RAM-constrained

# One entry per compartment. Each runs as its own model — cellpose applies ONE
# model/diameter per call, so nuclei and cytoplasm are two passes (still two model
# loads total, not two per image).
#   channel: index into the LAST axis for a multi-channel image (RGB: 0=R, 1=G, 2=B),
#            or None for an already-2D single-channel image.
#   diameter: expected object diameter in PIXELS. None = auto-estimate, which ONLY
#             works for the four models in AUTO_DIAMETER_MODELS below.
PASSES = [
    dict(name="nuclei", channel=2, model="nuclei", diameter=22.0,
         out_subdir="nuclei_masks", suffix="_nuclei",
         flow_threshold=0.4, cellprob_threshold=0.0),
    dict(name="cytoplasm", channel=0, model="cyto3", diameter=70.0,
         out_subdir="cytoplasm_masks", suffix="_cytoplasm",
         flow_threshold=0.4, cellprob_threshold=0.0),
]
USE_GPU = True
# ─────────────────────────────────────────────────────────────────────────────

# Only these four ship a size model, so only these support diameter=None
# (auto-estimate) via models.Cellpose. Every other v3 model must go through
# models.CellposeModel with an explicit diameter — the pass loop picks the class.
AUTO_DIAMETER_MODELS = {"cyto", "cyto2", "cyto3", "nuclei"}

# Verified working on this install. A name NOT in this set is the dangerous case:
# cellpose does not raise, it prints "model_type does not exist, using default
# model" and silently segments with the default instead — so a typo yields
# plausible-looking masks from the wrong model. We fail fast instead.
KNOWN_MODELS = AUTO_DIAMETER_MODELS | {
    "cyto2_cp3", "tissuenet_cp3", "livecell_cp3", "yeast_PhC_cp3", "yeast_BF_cp3",
    "bact_phase_cp3", "bact_fluor_cp3", "deepbacs_cp3", "neurips_grayscale_cyto2",
    "CP", "CPx", "TN1", "TN2", "TN3", "LC1", "LC2", "LC3", "LC4",
}
# These are listed by models.MODEL_NAMES but fail to load on this install
# (weight/state-dict mismatch). Don't use them.
BROKEN_MODELS = {"neurips_cellpose_default", "neurips_cellpose_transformer",
                 "transformer_cp3"}


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

for cfg in PASSES:
    out_dir = os.path.join(OUTPUT_DIR, cfg["out_subdir"])
    os.makedirs(out_dir, exist_ok=True)

    name = cfg["model"]
    if name in BROKEN_MODELS:
        raise SystemExit(
            f"VERIFICATION FAILED: model '{name}' is listed by cellpose but fails to "
            f"load on this install. Pick another model.")
    if name not in KNOWN_MODELS:
        raise SystemExit(
            f"VERIFICATION FAILED: unknown model '{name}'. cellpose would NOT raise — "
            f"it silently falls back to the default model and hands you masks from the "
            f"wrong one. Known models: {', '.join(sorted(KNOWN_MODELS))}.")
    if cfg["diameter"] is None and name not in AUTO_DIAMETER_MODELS:
        raise SystemExit(
            f"VERIFICATION FAILED: model '{name}' has no size model, so diameter=None "
            f"(auto-estimate) is impossible. Set an explicit diameter, or use one of: "
            f"{', '.join(sorted(AUTO_DIAMETER_MODELS))}.")

    # THE POINT OF THIS SCRIPT: one construction, reused for every image below.
    # models.Cellpose bundles the size model for auto-diameter but only exists for
    # the four AUTO_DIAMETER_MODELS; models.CellposeModel is the segmentation net
    # alone and works for every model, so it is the right class whenever a diameter
    # is given. Picking the wrong one is a FileNotFoundError on construction.
    if cfg["diameter"] is None:
        model = models.Cellpose(gpu=USE_GPU, model_type=name)
    else:
        model = models.CellposeModel(gpu=USE_GPU, model_type=name)
    print(f"[{cfg['name']}] model '{name}' loaded once "
          f"({type(model).__name__}); segmenting {len(files)} images", flush=True)

    written = 0
    for start in range(0, len(files), CHUNK):
        batch_files = files[start:start + CHUNK]
        planes = [load_channel(p, cfg["channel"]) for p in batch_files]
        # Cellpose.eval returns 4 values, CellposeModel.eval returns 3 — masks is
        # first either way, so index rather than unpack.
        masks = model.eval(
            planes,
            channels=[0, 0],                       # planes are already single-channel
            diameter=cfg["diameter"],
            flow_threshold=cfg["flow_threshold"],
            cellprob_threshold=cfg["cellprob_threshold"],
        )[0]
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

    del model  # free the GPU before the next pass loads its model

summary = os.path.join(OUTPUT_DIR, "cellpose_batch_summary.csv")
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

    # The count check above passes even on a totally failed pass: cellpose still
    # returns an (all-zero) mask per image, so a file gets written either way.
    # Zero objects EVERYWHERE means the config is wrong — wrong channel, diameter
    # far off, model mismatch — and that is a failure, not a result.
    if len(empty) == len(files):
        raise SystemExit(
            f"VERIFICATION FAILED: pass '{cfg['name']}' found 0 objects in ALL "
            f"{len(files)} images. Check channel={cfg['channel']}, "
            f"diameter={cfg['diameter']}, model='{cfg['model']}'.")

    # A few empties can be genuine (a faint or blank field), so warn rather than
    # fail — but never let them reach the summary table unannounced.
    if empty:
        print(f"[{cfg['name']}] WARNING: 0 objects in {len(empty)}/{len(files)} "
              f"images: {', '.join(empty)}")

print(f"Wrote {len(rows)} masks and {summary}")
