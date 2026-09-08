"""
WORKFLOW: two intensity channels + one label image -> per-object colocalisation CSV.

Runs in the MAIN env. Pearson, Manders, RWC (and optionally Costes) per object.

THE ARGUMENT ORDER IS THE OPPOSITE OF THE CORE MEASUREMENTS:
    core:        fn(masks, pixels)          <- labels FIRST
    correlation: fn(pixels_1, pixels_2, masks)  <- labels LAST
Getting it wrong does not raise. It returns numbers computed from the wrong arrays.
"""
import os

import numpy as np
import pandas as pd
from cp_measure.bulk import get_correlation_measurements

# ─────────────────────────── CONFIG ───────────────────────────
LABEL_PATH = "/app/data/labels.tif"    # integer LABEL image defining the objects
CH1_PATH = "/app/data/channel1.tif"    # e.g. protein A
CH2_PATH = "/app/data/channel2.tif"    # e.g. protein B
OUTPUT_CSV = "Colocalization.csv"
# Costes is by far the slowest measurement here. Enable only if explicitly asked for.
INCLUDE_COSTES = False
# ──────────────────────────────────────────────────────────────


def load_inputs():
    paths = (LABEL_PATH, CH1_PATH, CH2_PATH)
    if all(os.path.exists(p) for p in paths):
        import tifffile
        return (tifffile.imread(LABEL_PATH),
                tifffile.imread(CH1_PATH),
                tifffile.imread(CH2_PATH), False)

    print("WARNING: configured inputs not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    labels = np.zeros((128, 128), dtype=np.uint16)
    labels[10:50, 10:50] = 1      # object 1: channels correlated
    labels[70:120, 60:115] = 2    # object 2: channels anti-correlated
    ch1 = rng.random((128, 128))
    ch2 = ch1.copy()
    ch2[70:120, 60:115] = 1.0 - ch1[70:120, 60:115]
    return labels, ch1, ch2, True


def prepare(labels, ch1, ch2):
    if labels.dtype == bool:
        raise ValueError("VERIFICATION FAILED: labels is boolean — pass an integer LABEL image.")
    if not np.issubdtype(labels.dtype, np.integer):
        labels = labels.astype(np.uint16)
    if not (labels.shape == ch1.shape == ch2.shape):
        raise ValueError(
            f"VERIFICATION FAILED: shapes differ: labels {labels.shape}, "
            f"ch1 {ch1.shape}, ch2 {ch2.shape}"
        )
    # These functions are typed for float input; normalise integer channels.
    def to_float(a):
        a = a.astype(np.float64)
        return a / a.max() if a.max() > 1.0 else a
    return labels, to_float(ch1), to_float(ch2)


def main():
    labels, ch1, ch2, synthetic = load_inputs()
    labels, ch1, ch2 = prepare(labels, ch1, ch2)

    label_ids = np.unique(labels[labels > 0])
    n_objects = len(label_ids)
    print(f"objects: {n_objects}")
    if n_objects == 0:
        raise ValueError("VERIFICATION FAILED: label image contains no objects.")

    measurements = get_correlation_measurements()
    if not INCLUDE_COSTES:
        measurements.pop("costes", None)
    print(f"running: {sorted(measurements)}")

    results = {}
    for name, fn in measurements.items():
        # NOTE the order: pixels_1, pixels_2, masks
        results.update(fn(ch1, ch2, labels))

    # correlation returns dict[str, list[float]] (lists, not arrays)
    df = pd.DataFrame({k: np.asarray(v) for k, v in results.items()})
    df.insert(0, "label", label_ids)
    df.to_csv(OUTPUT_CSV, index=False)

    for _, row in df.iterrows():
        print(f"  label {int(row['label'])}: Pearson = {row['Correlation_Pearson']:.3f}")

    # ── verification: definitional invariants only ──
    if len(df) != n_objects:
        raise ValueError(f"VERIFICATION FAILED: {len(df)} rows for {n_objects} objects")
    pearson = df["Correlation_Pearson"].to_numpy()
    finite = pearson[np.isfinite(pearson)]
    if finite.size and (finite.min() < -1.0000001 or finite.max() > 1.0000001):
        raise ValueError(f"VERIFICATION FAILED: Pearson outside [-1,1]: {finite}")
    for col in df.columns:
        if col.startswith(("Correlation_Manders", "Correlation_RWC")):
            v = df[col].to_numpy()
            v = v[np.isfinite(v)]
            if v.size and (v.min() < -1e-6 or v.max() > 1.0000001):
                raise ValueError(f"VERIFICATION FAILED: {col} outside [0,1]")
    if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0:
        raise ValueError(f"VERIFICATION FAILED: {OUTPUT_CSV} missing or empty")

    # A NaN Pearson is legitimate for an object of constant intensity — report it.
    n_nan = int(np.isnan(pearson).sum())
    if n_nan:
        print(f"WARNING: {n_nan} objects have NaN Pearson (constant intensity?)")

    print(f"wrote {OUTPUT_CSV}: {len(df)} objects x {df.shape[1] - 1} features"
          + (" [SYNTHETIC DATA]" if synthetic else ""))


if __name__ == "__main__":
    main()
