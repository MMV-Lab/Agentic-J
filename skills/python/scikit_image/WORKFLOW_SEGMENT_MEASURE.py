"""
WORKFLOW: 2D image -> segmentation -> per-object measurement CSV (scikit-image).

Threshold -> clean -> watershed-split touching objects -> regionprops_table -> CSV.
Runs in the MAIN env. This is the default segmentation recipe for scientific
(16-bit / float) images.

Verified end-to-end. Run untouched to segment synthetic cells.
"""
import os

import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from skimage import feature, filters, measure, morphology, segmentation

# ─────────────────────────── CONFIG ───────────────────────────
IMAGE_PATH = "/app/data/cells.tif"
OUTPUT_CSV = "Measurements.csv"
LABEL_TIFF = "labels.tif"          # saved so a later stage can reuse the labels
PIXEL_SIZE_UM = None               # e.g. 0.325 from PROJECT STATE; None = report px
GAUSSIAN_SIGMA = 1.0
MIN_OBJECT_SIZE = 64               # px; removes debris
SPLIT_TOUCHING = True              # watershed on the distance transform
MIN_SEED_DISTANCE = 7              # raise to merge over-segmented seeds
REMOVE_BORDER_OBJECTS = True       # objects clipped by the edge bias every statistic
# ──────────────────────────────────────────────────────────────

PROPERTIES = (
    "label", "area", "perimeter", "eccentricity", "solidity", "extent",
    "axis_major_length", "axis_minor_length", "equivalent_diameter_area",
    "orientation", "centroid",
    "intensity_mean", "intensity_max", "intensity_min", "intensity_std",
)


def load_image():
    if os.path.exists(IMAGE_PATH):
        import tifffile
        return tifffile.imread(IMAGE_PATH), False

    print("WARNING: configured input not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    img = np.zeros((256, 256), dtype=np.uint16)
    yy, xx = np.ogrid[:256, :256]
    centres = [(50, 50), (50, 130), (140, 60), (150, 150), (152, 170), (200, 100)]
    for cy, cx in centres:
        img[(yy - cy) ** 2 + (xx - cx) ** 2 < 18 ** 2] = 3000
    img = (img + rng.normal(0, 80, img.shape)).clip(0, 65535).astype(np.uint16)
    return img, True


def segment(img):
    # preserve_range=True: without it gaussian rescales to [0,1] and every
    # intensity measurement below becomes meaningless.
    smooth = filters.gaussian(img, sigma=GAUSSIAN_SIGMA, preserve_range=True)

    thresh = filters.threshold_otsu(smooth)
    binary = smooth > thresh
    print(f"otsu threshold = {thresh:.1f}, foreground = {binary.mean():.1%}")

    # max_size=, NOT min_size= (deprecated in 0.26). max_size removes area <= N.
    binary = morphology.remove_small_objects(binary, max_size=MIN_OBJECT_SIZE)
    # closing(), NOT binary_closing() (deprecated in 0.26).
    binary = morphology.closing(binary, morphology.disk(2))

    n_components = ndi.label(binary)[1]
    print(f"connected components: {n_components}")

    if SPLIT_TOUCHING:
        distance = ndi.distance_transform_edt(binary)
        # peak_local_max returns COORDINATES (not a bool image) since 0.20
        coords = feature.peak_local_max(
            distance, min_distance=MIN_SEED_DISTANCE, labels=binary
        )
        markers = np.zeros(distance.shape, dtype=bool)
        markers[tuple(coords.T)] = True
        markers, n_seeds = ndi.label(markers)
        print(f"watershed: {n_seeds} seeds")
        # Zero seeds does not raise — watershed would return one label for everything.
        if n_seeds == 0:
            raise ValueError(
                f"VERIFICATION FAILED: no watershed seeds. MIN_SEED_DISTANCE="
                f"{MIN_SEED_DISTANCE} is too large for these objects."
            )
        if n_seeds > 5 * max(n_components, 1):
            print(f"WARNING: {n_seeds} seeds for {n_components} components — "
                  f"likely over-segmenting. Raise MIN_SEED_DISTANCE.")
        labels = segmentation.watershed(-distance, markers, mask=binary)
    else:
        labels = measure.label(binary)

    if REMOVE_BORDER_OBJECTS:
        before = labels.max()
        labels = segmentation.clear_border(labels)
        print(f"removed {before - len(np.unique(labels[labels > 0]))} border objects")

    # Filtering leaves gapped ids ([1, 3, 7]); make them contiguous 1..N.
    labels, _, _ = segmentation.relabel_sequential(labels)
    return labels


def main():
    img, synthetic = load_image()
    print(f"image {img.shape} {img.dtype}, range [{img.min()}, {img.max()}]")

    labels = segment(img)
    n_objects = len(np.unique(labels[labels > 0]))
    print(f"objects: {n_objects}")
    if n_objects == 0:
        raise ValueError("VERIFICATION FAILED: segmentation produced no objects.")

    # spacing= converts to physical units directly; otherwise everything is in pixels.
    spacing = (PIXEL_SIZE_UM, PIXEL_SIZE_UM) if PIXEL_SIZE_UM else None
    props = measure.regionprops_table(
        labels, intensity_image=img, properties=PROPERTIES, spacing=spacing
    )
    df = pd.DataFrame(props)

    if PIXEL_SIZE_UM:
        df = df.rename(columns={"area": "area_um2", "perimeter": "perimeter_um"})
        print(f"units: microns (pixel size {PIXEL_SIZE_UM} um/px)")
    else:
        print("WARNING: PIXEL_SIZE_UM is None — area is px^2, lengths are px.")

    df.to_csv(OUTPUT_CSV, index=False)

    import tifffile
    tifffile.imwrite(LABEL_TIFF, labels.astype(np.uint16))

    # ── verification: invariants that are ALWAYS true for a correct run ──
    if len(df) != n_objects:
        raise ValueError(f"VERIFICATION FAILED: {len(df)} rows for {n_objects} objects")
    area_col = "area_um2" if PIXEL_SIZE_UM else "area"
    if (df[area_col] <= 0).any():
        raise ValueError("VERIFICATION FAILED: non-positive area")
    if not (0 <= df["eccentricity"]).all() or not (df["eccentricity"] <= 1).all():
        raise ValueError("VERIFICATION FAILED: eccentricity outside [0,1]")
    if not (0 <= df["solidity"]).all() or not (df["solidity"] <= 1.0000001).all():
        raise ValueError("VERIFICATION FAILED: solidity outside [0,1]")
    for path in (OUTPUT_CSV, LABEL_TIFF):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise ValueError(f"VERIFICATION FAILED: {path} missing or empty")

    if n_objects < 3:
        print(f"WARNING: only {n_objects} objects — statistics on this will be weak.")

    print(f"mean {area_col} = {df[area_col].mean():.1f}")
    print(f"wrote {OUTPUT_CSV} ({len(df)} objects) and {LABEL_TIFF}"
          + (" [SYNTHETIC DATA]" if synthetic else ""))


if __name__ == "__main__":
    main()
