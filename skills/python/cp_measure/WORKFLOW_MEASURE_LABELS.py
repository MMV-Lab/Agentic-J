"""
WORKFLOW: label image + intensity image -> 271-feature per-object CSV (cp_measure).

Runs in the MAIN env. Copy this file, edit the CONFIG block, delete the synthetic
fallback, and hand the CSV to the statistics stage.

Verified end-to-end. Run it untouched and it segments synthetic data so you can see
the shape of the output before pointing it at real files.
"""
import os

import numpy as np
import pandas as pd
from cp_measure.bulk import get_core_measurements

# ─────────────────────────── CONFIG ───────────────────────────
LABEL_PATH = "/app/data/labels.tif"      # integer LABEL image (0 = background)
IMAGE_PATH = "/app/data/intensity.tif"   # matching intensity image
OUTPUT_CSV = "Measurements.csv"
PIXEL_SIZE_UM = None                     # e.g. 0.325 from PROJECT STATE; None = report px
# Restrict to a subset to save time, e.g. ("sizeshape", "intensity", "feret").
# None = all 8 groups (271 features).
GROUPS = None
# ──────────────────────────────────────────────────────────────


def load_inputs():
    """Load the configured images, or synthesise a 2-object example if absent."""
    if os.path.exists(LABEL_PATH) and os.path.exists(IMAGE_PATH):
        import tifffile
        labels = tifffile.imread(LABEL_PATH)
        pixels = tifffile.imread(IMAGE_PATH)
        return labels, pixels, False

    print("WARNING: configured inputs not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    labels = np.zeros((128, 128), dtype=np.uint16)
    labels[10:50, 10:50] = 1
    labels[70:120, 60:115] = 2
    pixels = (rng.random((128, 128)) * 65535).astype(np.uint16)
    return labels, pixels, True


def prepare(labels, pixels):
    """Enforce the two contracts cp_measure will not enforce for you."""
    # A boolean mask is silently measured as ONE object.
    if labels.dtype == bool:
        raise ValueError(
            "VERIFICATION FAILED: labels is boolean. cp_measure would measure the whole "
            "foreground as a single object. Run skimage.measure.label() first."
        )
    if not np.issubdtype(labels.dtype, np.integer):
        labels = labels.astype(np.uint16)

    # texture -> skimage.util.img_as_ubyte rejects floats outside [-1, 1].
    if np.issubdtype(pixels.dtype, np.floating) and pixels.max() > 1.0:
        print(f"scaling float image (max={pixels.max():.1f}) into [0,1] for texture")
        pixels = pixels / pixels.max()

    if labels.shape != pixels.shape:
        raise ValueError(
            f"VERIFICATION FAILED: label shape {labels.shape} != image shape {pixels.shape}"
        )
    return labels, pixels


def main():
    labels, pixels, synthetic = load_inputs()
    labels, pixels = prepare(labels, pixels)

    label_ids = np.unique(labels[labels > 0])
    n_objects = len(label_ids)
    print(f"labels {labels.shape} {labels.dtype} | image {pixels.shape} {pixels.dtype}")
    print(f"objects: {n_objects}")
    if n_objects == 0:
        raise ValueError("VERIFICATION FAILED: label image contains no objects.")

    # sanitize=True (default) tolerates gapped label ids like [1, 3, 7].
    measurements = get_core_measurements()
    if GROUPS is not None:
        measurements = {k: measurements[k] for k in GROUPS}

    results = {}
    for name, fn in measurements.items():
        results.update(fn(labels, pixels))       # core order: (masks, pixels)
    print(f"features computed: {len(results)}")

    df = pd.DataFrame(results)
    df.insert(0, "label", label_ids)

    # Areas and lengths come out in PIXELS. Convert only if we were told the scale.
    if PIXEL_SIZE_UM is not None:
        if "Area" in df:
            df["Area_um2"] = df["Area"] * (PIXEL_SIZE_UM ** 2)
        for col in ("Perimeter", "MajorAxisLength", "MinorAxisLength",
                    "EquivalentDiameter", "MaxFeretDiameter", "MinFeretDiameter"):
            if col in df:
                df[f"{col}_um"] = df[col] * PIXEL_SIZE_UM
        print(f"converted to microns with pixel size {PIXEL_SIZE_UM} um/px")
    else:
        print("WARNING: PIXEL_SIZE_UM is None — all sizes reported in PIXELS.")

    df.to_csv(OUTPUT_CSV, index=False)

    # ── verification: invariants that are ALWAYS true for a correct run ──
    if len(df) != n_objects:
        raise ValueError(f"VERIFICATION FAILED: {len(df)} rows for {n_objects} objects")
    if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0:
        raise ValueError(f"VERIFICATION FAILED: {OUTPUT_CSV} missing or empty")
    if "Area" in df and (df["Area"] <= 0).any():
        raise ValueError("VERIFICATION FAILED: non-positive Area")

    # NaNs can be legitimate (e.g. texture of a uniform object) — report, never assert.
    n_nan = int(df.isna().sum().sum())
    if n_nan:
        print(f"WARNING: {n_nan} NaN values present (can be legitimate for uniform objects)")

    print(f"wrote {OUTPUT_CSV}: {len(df)} objects x {df.shape[1] - 1} features"
          + (" [SYNTHETIC DATA]" if synthetic else ""))


if __name__ == "__main__":
    main()
