"""
WORKFLOW: spot channel + cell/nucleus LABEL image -> spots-per-cell CSV.

The standard smFISH readout: how many transcripts does each cell contain. Detection
needs no parameter tuning (automatic threshold); the labels come from an upstream
segmentation step (cellpose / stardist / labkit), NOT from this script.

Runs in the MAIN env. Copy this file, edit the CONFIG block, delete the synthetic
fallback, and hand SpotsPerCell.csv to the statistics stage.

Verified end-to-end. Run it untouched and it works on synthetic data so you can see
the shape of the output before pointing it at real files.
"""
import os

import numpy as np
import pandas as pd

import bigfish.detection as detection

# ─────────────────────────── CONFIG ───────────────────────────
IMAGE_PATH = "/app/data/spots.tif"    # the SPOT channel (2D or 3D)
LABEL_PATH = "/app/data/labels.tif"   # integer LABEL image, 0 = background.
                                      # Must match IMAGE_PATH in y/x.

# NANOMETRES, ordered (z, y, x) for 3D or (y, x) for 2D. See SKILL.md pitfall B1.
VOXEL_SIZE_NM = (100, 100)
SPOT_RADIUS_NM = (150, 150)

OUTPUT_CSV = "SpotsPerCell.csv"
# ──────────────────────────────────────────────────────────────


def load_inputs():
    """Load the configured images, or synthesise a 3-cell example if absent."""
    if os.path.exists(IMAGE_PATH) and os.path.exists(LABEL_PATH):
        import tifffile
        return tifffile.imread(IMAGE_PATH), tifffile.imread(LABEL_PATH), False

    print("WARNING: configured inputs not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    h = w = 512
    image = np.full((h, w), 100.0)
    labels = np.zeros((h, w), dtype=np.uint16)
    yy, xx = np.mgrid[0:h, 0:w]

    # three round "cells", each seeded with a different number of spots
    for cell_id, (cy, cx, r, n_spots) in enumerate(
            [(130, 130, 90, 12), (130, 380, 90, 5), (380, 250, 100, 20)], start=1):
        labels[((yy - cy) ** 2 + (xx - cx) ** 2) <= r ** 2] = cell_id
        for _ in range(n_spots):
            while True:
                sy, sx = rng.uniform(cy - r, cy + r), rng.uniform(cx - r, cx + r)
                if (sy - cy) ** 2 + (sx - cx) ** 2 <= (r - 12) ** 2:
                    break
            image += 900.0 * np.exp(-(((yy - sy) ** 2 + (xx - sx) ** 2) / (2 * 1.4 ** 2)))

    image += rng.normal(0, 12, image.shape)
    return np.clip(image, 0, 65535).astype(np.uint16), labels, True


def assign_spots_to_labels(spots, labels):
    """
    Look up each spot's label. Spot coords are (z,y,x)/(y,x) integer indices, so they
    index the label image directly — but a 3D detection against a 2D label image must
    drop z first (pitfall B3).
    """
    if len(spots) == 0:
        return np.empty(0, dtype=labels.dtype)

    coords = spots[:, -labels.ndim:] if spots.shape[1] > labels.ndim else spots
    coords = np.rint(coords).astype(int)          # tolerate sub-pixel input
    for axis in range(labels.ndim):               # guard against off-by-one at the border
        coords[:, axis] = np.clip(coords[:, axis], 0, labels.shape[axis] - 1)
    return labels[tuple(coords[:, a] for a in range(labels.ndim))]


def main():
    image, labels, synthetic = load_inputs()
    print(f"image {image.ndim}D {image.shape} {image.dtype} | labels {labels.shape} "
          f"({labels.max()} objects)")

    if min(VOXEL_SIZE_NM) < 10 or min(SPOT_RADIUS_NM) < 10:
        raise ValueError(
            f"VOXEL_SIZE_NM={VOXEL_SIZE_NM}, SPOT_RADIUS_NM={SPOT_RADIUS_NM} look like "
            "MICRONS or PIXELS — both must be in NANOMETRES (pitfall B1).")

    spots, threshold = detection.detect_spots(
        images=image,
        threshold=None,              # ← automatic. Do not hand-tune.
        return_threshold=True,
        voxel_size=VOXEL_SIZE_NM,
        spot_radius=SPOT_RADIUS_NM)
    print(f"{len(spots)} spots detected (automatic threshold = {threshold})")

    spot_labels = assign_spots_to_labels(spots, labels)

    cell_ids = np.arange(1, int(labels.max()) + 1)
    counts = np.array([(spot_labels == cid).sum() for cid in cell_ids])
    areas = np.array([(labels == cid).sum() for cid in cell_ids])

    df = pd.DataFrame({
        "cell_id": cell_ids,
        "n_spots": counts,
        "cell_area_px": areas,
        "spots_per_1000px": np.where(areas > 0, counts / areas * 1000, np.nan).round(3),
    })
    df.to_csv(OUTPUT_CSV, index=False)

    n_bg = int((spot_labels == 0).sum())
    print(df.to_string(index=False))
    print(f"\n{n_bg} spot(s) fell outside every cell (label 0) and are excluded.")
    print(f"wrote {OUTPUT_CSV}")

    if synthetic:
        print("\nNOTE: synthetic data — seeded with 12, 5 and 20 spots respectively.")
        print("Detected counts may run 1-2 low per cell: the seeding is random, so some")
        print("spots land closer than the minimum separation and merge into one maximum.")
        print("Set IMAGE_PATH and LABEL_PATH to real files.")


if __name__ == "__main__":
    main()
