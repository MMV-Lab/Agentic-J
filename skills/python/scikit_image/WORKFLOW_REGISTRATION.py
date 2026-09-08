"""
WORKFLOW: correct rigid drift across a (T, Y, X) stack with phase_cross_correlation.

Runs in the MAIN env. RIGID TRANSLATION ONLY. For rotation, scale, or elastic
deformation use the Fiji TurboReg/StackReg plugins via the Groovy coder.

Verified end-to-end. Run untouched: it builds a stack with known shifts and recovers them.
"""
import os

import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from skimage.registration import phase_cross_correlation

# ─────────────────────────── CONFIG ───────────────────────────
STACK_PATH = "/app/data/timelapse.tif"   # (T, Y, X)
OUTPUT_TIFF = "registered.tif"
SHIFTS_CSV = "Drift_Shifts.csv"
UPSAMPLE_FACTOR = 10        # 10 -> 1/10-pixel precision
REFERENCE = "first"         # "first" (fixed ref) or "previous" (sequential, drifts)
# ──────────────────────────────────────────────────────────────


def load_stack():
    if os.path.exists(STACK_PATH):
        import tifffile
        stack = tifffile.imread(STACK_PATH)
        if stack.ndim != 3:
            raise ValueError(f"VERIFICATION FAILED: expected (T,Y,X), got {stack.shape}")
        return stack, None, False

    print("WARNING: configured input not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    base = np.zeros((128, 128), dtype=np.float64)
    yy, xx = np.ogrid[:128, :128]
    for cy, cx in [(40, 40), (80, 70), (60, 100)]:
        base[(yy - cy) ** 2 + (xx - cx) ** 2 < 10 ** 2] = 1.0
    base += rng.normal(0, 0.02, base.shape)

    true_shifts = [(0, 0), (3, -2), (6, -5), (8, -4), (11, -7)]
    stack = np.stack([ndi.shift(base, s, order=1) for s in true_shifts])
    return stack, true_shifts, True


def main():
    stack, true_shifts, synthetic = load_stack()
    n_frames = len(stack)
    print(f"stack {stack.shape} {stack.dtype}, {n_frames} frames")
    if n_frames < 2:
        raise ValueError("VERIFICATION FAILED: need >= 2 frames to register.")

    registered = np.empty_like(stack, dtype=np.float64)
    registered[0] = stack[0]
    rows = [{"frame": 0, "shift_y": 0.0, "shift_x": 0.0, "error": 0.0}]

    cumulative = np.zeros(2)
    for t in range(1, n_frames):
        reference = stack[0] if REFERENCE == "first" else stack[t - 1]
        # shift moves `moving` onto `reference`
        shift, error, _ = phase_cross_correlation(
            reference, stack[t], upsample_factor=UPSAMPLE_FACTOR
        )
        if REFERENCE == "previous":
            cumulative += shift
            applied = cumulative.copy()
        else:
            applied = shift
        registered[t] = ndi.shift(stack[t], applied, order=1)
        rows.append({"frame": t, "shift_y": float(applied[0]),
                     "shift_x": float(applied[1]), "error": float(error)})
        print(f"  frame {t}: shift = ({applied[0]:+.2f}, {applied[1]:+.2f}) px, "
              f"error = {error:.4f}")

    df = pd.DataFrame(rows)
    df.to_csv(SHIFTS_CSV, index=False)

    import tifffile
    tifffile.imwrite(OUTPUT_TIFF, registered.astype(np.float32))

    # ── verification: invariants ──
    if len(df) != n_frames:
        raise ValueError(f"VERIFICATION FAILED: {len(df)} rows for {n_frames} frames")
    if registered.shape != stack.shape:
        raise ValueError("VERIFICATION FAILED: registered stack changed shape")
    for path in (SHIFTS_CSV, OUTPUT_TIFF):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise ValueError(f"VERIFICATION FAILED: {path} missing or empty")

    if synthetic and true_shifts is not None:
        # recovered shift should be the NEGATIVE of the shift that was applied
        recovered = df[["shift_y", "shift_x"]].to_numpy()
        expected = -np.array(true_shifts, dtype=float)
        max_err = np.abs(recovered - expected).max()
        print(f"synthetic check: max deviation from known shifts = {max_err:.3f} px")
        if max_err > 0.5:
            raise ValueError(
                f"VERIFICATION FAILED: recovered shifts differ from ground truth by {max_err:.3f} px"
            )

    # NOTE: the `error` from phase_cross_correlation is a normalised, translation-
    # invariant RMS difference — NOT a 0-is-good quality score. With the default
    # normalization="phase" it sits at ~1.0 even for a perfect registration (verified:
    # exact recovery of known shifts with error == 1.0000). Record it; never threshold
    # on it. To judge a registration, compare frames before/after, or check that the
    # shifts vary smoothly over time.

    print(f"wrote {OUTPUT_TIFF} and {SHIFTS_CSV}"
          + (" [SYNTHETIC DATA]" if synthetic else ""))


if __name__ == "__main__":
    main()
