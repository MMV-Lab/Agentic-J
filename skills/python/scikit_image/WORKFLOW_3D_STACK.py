"""
WORKFLOW: 3D (Z, Y, X) volume -> segmentation -> per-object measurement CSV.

Runs in the MAIN env. The 2D recipe does NOT transfer unchanged:
  - footprints must be morphology.ball(r), not disk(r)
  - spacing=(dz, dy, dx) is REQUIRED for anisotropic voxels, or `area` (the volume)
    is silently wrong
  - `eccentricity` and `perimeter` raise NotImplementedError on 3D labels

Verified end-to-end. Run untouched to segment a synthetic volume.
"""
import os

import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from skimage import feature, filters, measure, morphology, segmentation

# ─────────────────────────── CONFIG ───────────────────────────
VOLUME_PATH = "/app/data/volume.tif"     # (Z, Y, X)
OUTPUT_CSV = "Measurements_3D.csv"
# Voxel size in microns as (dz, dy, dx). Confocal stacks are almost always
# anisotropic (z step >> xy pixel). None = report in voxels.
VOXEL_SIZE_UM = None                      # e.g. (2.0, 0.325, 0.325)
GAUSSIAN_SIGMA = 1.0
MIN_OBJECT_VOXELS = 100
SPLIT_TOUCHING = True
# Sharp knob. Too small shatters each object; too large yields ZERO seeds and
# watershed then returns one label for everything. Neither raises. Compare the
# seed count against the connected-component count printed below.
MIN_SEED_DISTANCE = 7
# ──────────────────────────────────────────────────────────────

# NOTE: no eccentricity, no perimeter — both raise NotImplementedError in 3D.
PROPERTIES_3D = (
    "label", "area", "solidity", "extent", "euler_number",
    "axis_major_length", "axis_minor_length", "equivalent_diameter_area",
    "feret_diameter_max", "centroid",
    "intensity_mean", "intensity_max", "intensity_min", "intensity_std",
)


def load_volume():
    if os.path.exists(VOLUME_PATH):
        import tifffile
        vol = tifffile.imread(VOLUME_PATH)
        if vol.ndim != 3:
            raise ValueError(f"VERIFICATION FAILED: expected (Z,Y,X), got {vol.shape}")
        return vol, False

    print("WARNING: configured input not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    vol = np.zeros((24, 96, 96), dtype=np.uint16)
    zz, yy, xx = np.ogrid[:24, :96, :96]
    for cz, cy, cx in [(8, 25, 25), (12, 60, 30), (14, 40, 70)]:
        vol[((zz - cz) ** 2) * 4 + (yy - cy) ** 2 + (xx - cx) ** 2 < 12 ** 2] = 3000
    vol = (vol + rng.normal(0, 60, vol.shape)).clip(0, 65535).astype(np.uint16)
    return vol, True


def segment_3d(vol):
    smooth = filters.gaussian(vol, sigma=GAUSSIAN_SIGMA, preserve_range=True)
    thresh = filters.threshold_otsu(smooth)
    binary = smooth > thresh
    print(f"otsu threshold = {thresh:.1f}, foreground = {binary.mean():.1%}")

    # max_size=, NOT min_size= (deprecated in 0.26). max_size removes area <= N.
    binary = morphology.remove_small_objects(binary, max_size=MIN_OBJECT_VOXELS)
    # ball(), not disk() — and closing(), not the deprecated binary_closing().
    binary = morphology.closing(binary, morphology.ball(1))

    n_components = ndi.label(binary)[1]
    print(f"connected components: {n_components}")

    if SPLIT_TOUCHING:
        # sampling= makes the distance transform respect anisotropic voxels, which
        # also makes MIN_SEED_DISTANCE behave consistently in physical units.
        sampling = VOXEL_SIZE_UM if VOXEL_SIZE_UM else None
        distance = ndi.distance_transform_edt(binary, sampling=sampling)
        coords = feature.peak_local_max(
            distance, min_distance=MIN_SEED_DISTANCE, labels=binary
        )
        markers = np.zeros(distance.shape, dtype=bool)
        markers[tuple(coords.T)] = True
        markers, n_seeds = ndi.label(markers)
        print(f"watershed: {n_seeds} seeds")
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

    labels, _, _ = segmentation.relabel_sequential(labels)
    return labels


def main():
    vol, synthetic = load_volume()
    print(f"volume {vol.shape} {vol.dtype} (Z, Y, X)")

    labels = segment_3d(vol)
    n_objects = len(np.unique(labels[labels > 0]))
    print(f"objects: {n_objects}")
    if n_objects == 0:
        raise ValueError("VERIFICATION FAILED: segmentation produced no objects.")

    props = measure.regionprops_table(
        labels, intensity_image=vol, properties=PROPERTIES_3D, spacing=VOXEL_SIZE_UM
    )
    df = pd.DataFrame(props)

    # In 3D, `area` is the VOLUME.
    if VOXEL_SIZE_UM:
        df = df.rename(columns={"area": "volume_um3"})
        volume_col = "volume_um3"
        print(f"units: microns (voxel size {VOXEL_SIZE_UM} um)")
    else:
        df = df.rename(columns={"area": "volume_voxels"})
        volume_col = "volume_voxels"
        print("WARNING: VOXEL_SIZE_UM is None — volume reported in VOXELS. "
              "A confocal z-step is rarely equal to the xy pixel size.")

    df.to_csv(OUTPUT_CSV, index=False)

    # ── verification: invariants ──
    if len(df) != n_objects:
        raise ValueError(f"VERIFICATION FAILED: {len(df)} rows for {n_objects} objects")
    if (df[volume_col] <= 0).any():
        raise ValueError("VERIFICATION FAILED: non-positive volume")
    if not (df["solidity"] <= 1.0000001).all():
        raise ValueError("VERIFICATION FAILED: solidity > 1")
    if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0:
        raise ValueError(f"VERIFICATION FAILED: {OUTPUT_CSV} missing or empty")

    if n_objects < 3:
        print(f"WARNING: only {n_objects} objects — statistics on this will be weak.")

    print(f"mean {volume_col} = {df[volume_col].mean():.1f}")
    print(f"wrote {OUTPUT_CSV}: {len(df)} objects x {df.shape[1] - 1} features"
          + (" [SYNTHETIC DATA]" if synthetic else ""))


if __name__ == "__main__":
    main()
