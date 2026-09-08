"""
WORKFLOW: fluorescence image(s) -> spot coordinates CSV + per-image counts + elbow QC plot.

No parameter tuning: the intensity threshold is chosen automatically (elbow method).
You only set the two PHYSICAL values in the CONFIG block, both in NANOMETRES.

Runs in the MAIN env. Copy this file, edit the CONFIG block, delete the synthetic
fallback, and hand Counts.csv to the statistics stage.

Verified end-to-end. Run it untouched and it detects spots in synthetic data so you
can see the shape of the output before pointing it at real files.
"""
import os
import glob

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import bigfish.detection as detection

# ─────────────────────────── CONFIG ───────────────────────────
# A single image file, or a FOLDER. A folder is processed in batch with ONE shared
# threshold, which is what makes counts comparable across the set (pitfall B7).
INPUT_PATH = "/app/data/spots.tif"

# Both in NANOMETRES, ordered (z, y, x) for 3D or (y, x) for 2D — z first, x last.
#
# VOXEL_SIZE_NM: the acquisition pixel size / z-step. READ it from the image
#   calibration or the acquisition metadata — never guess. A plausible-but-wrong
#   value (e.g. 100 when the truth is 322) passes every sanity check and silently
#   corrupts detection. `WORKFLOW_SPOT_SEGMENTATION.py` has `read_pixel_size_nm()`
#   which parses the TIFF/ImageJ calibration and raises instead of falling back.
#
# SPOT_RADIUS_NM: the actual radius of YOUR objects. 150 nm is right ONLY for
#   diffraction-limited puncta. For anything larger (granules, parasites, vesicles)
#   measure it — a radius that does not match the objects silently wrecks detection.
#   `WORKFLOW_SPOT_SEGMENTATION.py` has `measure_object_radius_nm()`.
VOXEL_SIZE_NM = (100, 100)
SPOT_RADIUS_NM = (150, 150)

SUBPIXEL = False              # True -> Gaussian-fit to float coords (needed for distances, not counts)
OUTPUT_SPOTS_CSV = "Spots.csv"
OUTPUT_COUNTS_CSV = "Counts.csv"
QC_PLOT = "Elbow_QC.png"      # None to skip. ALWAYS look at this before trusting a count.
# ──────────────────────────────────────────────────────────────


def load_inputs():
    """Load the configured image(s), or synthesise a spot field if absent."""
    if os.path.isdir(INPUT_PATH):
        import tifffile
        paths = sorted(
            p for ext in ("*.tif", "*.tiff") for p in glob.glob(os.path.join(INPUT_PATH, ext))
        )
        if paths:
            return [tifffile.imread(p) for p in paths], [os.path.basename(p) for p in paths], False
    elif os.path.exists(INPUT_PATH):
        import tifffile
        return [tifffile.imread(INPUT_PATH)], [os.path.basename(INPUT_PATH)], False

    print("WARNING: configured input not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    images = []
    for _ in range(2):
        h = w = 512
        img = np.full((h, w), 100.0)
        yy, xx = np.mgrid[0:h, 0:w]
        for y in range(40, h - 40, 60):
            for x in range(40, w - 40, 60):
                img += 900.0 * np.exp(-(((yy - y) ** 2 + (xx - x) ** 2) / (2 * 1.4 ** 2)))
        img += rng.normal(0, 12, img.shape)
        images.append(np.clip(img, 0, 65535).astype(np.uint16))
    return images, ["synthetic_1.tif", "synthetic_2.tif"], True


def check_units(image, voxel_size, spot_radius):
    """Catch the nanometre/micron mix-up (pitfall B1) before it silently ruins the run."""
    ndim = image.ndim
    if len(voxel_size) != ndim or len(spot_radius) != ndim:
        raise ValueError(
            f"image is {ndim}D so VOXEL_SIZE_NM and SPOT_RADIUS_NM must both have {ndim} "
            f"entries, ordered {'(z, y, x)' if ndim == 3 else '(y, x)'}; "
            f"got {voxel_size} and {spot_radius}")
    if min(voxel_size) < 10 or min(spot_radius) < 10:
        raise ValueError(
            f"VOXEL_SIZE_NM={voxel_size}, SPOT_RADIUS_NM={spot_radius} look like MICRONS or "
            "PIXELS. Both must be in NANOMETRES (e.g. 0.1 um -> 100).")


def detect(images):
    """One automatic threshold shared across every image (pitfall B7)."""
    for img in images:
        check_units(img, VOXEL_SIZE_NM, SPOT_RADIUS_NM)

    spots_list, threshold = detection.detect_spots(
        images=images,
        threshold=None,              # ← automatic. Do not hand-tune.
        return_threshold=True,
        voxel_size=VOXEL_SIZE_NM,
        spot_radius=SPOT_RADIUS_NM)

    if not isinstance(spots_list, list):      # single-image input returns a bare array
        spots_list = [spots_list]

    if SUBPIXEL:
        spots_list = [
            detection.fit_subpixel(img, s, VOXEL_SIZE_NM, SPOT_RADIUS_NM)
            for img, s in zip(images, spots_list)
        ]
    return spots_list, threshold


def to_frame(spots_list, names):
    """Flatten to a tidy table, converting (z,y,x) order to x/y/z columns (pitfall B3)."""
    rows = []
    for name, spots in zip(names, spots_list):
        if len(spots) == 0:
            continue
        df = pd.DataFrame({
            "image": name,
            "x": spots[:, -1],
            "y": spots[:, -2],
        })
        if spots.shape[1] == 3:
            df["z"] = spots[:, 0]
        rows.append(df)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["image", "x", "y"])


def qc_plot(images, threshold, path):
    """Elbow curve. A clean bend = the automatic threshold is trustworthy (pitfall B8)."""
    thresholds, log_counts, auto = detection.get_elbow_values(
        images=images, voxel_size=VOXEL_SIZE_NM, spot_radius=SPOT_RADIUS_NM)
    # get_elbow_values returns counts already on a LOG scale (and smoothed), so
    # exponentiate to plot real spot counts — do NOT also set a log y-axis.
    counts = np.exp(log_counts)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(thresholds, counts, color="#4C6EF5", lw=1.8)
    ax.axvline(auto, color="#E8590C", ls="--", lw=1.5, label=f"auto threshold = {auto:.3g}")
    ax.set_xlabel("intensity threshold")
    ax.set_ylabel("detected spots (smoothed)")
    ax.set_yscale("log")
    ax.set_title("Automatic threshold selection (elbow)")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"wrote {path}  (check for a clear bend at the dashed line)")


def main():
    images, names, synthetic = load_inputs()
    print(f"{len(images)} image(s); first is {images[0].ndim}D {images[0].shape} {images[0].dtype}")

    spots_list, threshold = detect(images)
    print(f"automatic threshold = {threshold}")

    counts = pd.DataFrame({
        "image": names,
        "n_spots": [len(s) for s in spots_list],
    })
    print(counts.to_string(index=False))

    to_frame(spots_list, names).to_csv(OUTPUT_SPOTS_CSV, index=False)
    counts.to_csv(OUTPUT_COUNTS_CSV, index=False)
    print(f"wrote {OUTPUT_SPOTS_CSV} and {OUTPUT_COUNTS_CSV}")

    if QC_PLOT:
        qc_plot(images, threshold, QC_PLOT)

    if synthetic:
        print("\nNOTE: these numbers are from SYNTHETIC data. Set INPUT_PATH to real files.")


if __name__ == "__main__":
    main()
