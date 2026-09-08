"""
WORKFLOW: correlation + multi-feature screening -> Statistics_Results.csv  (STAGE 1)

Runs in the MAIN env. THIS SCRIPT DOES NOT PLOT.

Two jobs, both of which are done wrong by default:

  1. ONE CORRELATION, the right coefficient.
     Pearson measures a LINEAR relationship and is wrecked by a single outlier.
     Spearman measures a MONOTONIC one and is not. This script reports both, and
     reports the number of IQR outliers so the reader can judge.

  2. MANY CORRELATIONS (screening cp_measure's 271 features against one variable).
     At alpha=0.05, ~14 of 271 pure-noise features come out "significant". Measured on
     50 noise comparisons: 2/50 pass raw p<0.05, 0/50 survive Benjamini-Hochberg.
     Screening WITHOUT FDR correction manufactures findings. Both raw and adjusted
     p-values are written to the CSV.

NOTE ON IMPORTS: when the Supervisor executes this via execute_script, pd/np/stats are
already in scope. The explicit imports are redundant there but harmless, and let you run
this file directly.
"""
import os

import numpy as np
import pandas as pd
from scipy import stats

# ─────────────────────────── CONFIG ───────────────────────────
INPUT_CSV = "/app/data/Measurements.csv"
OUTPUT_CSV = "Statistics_Results.csv"
SCREEN_CSV = "Correlation_Screen.csv"     # written only when SCREEN_ALL_FEATURES

TARGET_COLUMN = "Intensity_MeanIntensity"   # the variable everything is correlated with
PRIMARY_COLUMN = "area_um2"                 # the one pre-planned correlation

# Screen every numeric column against TARGET_COLUMN, with BH correction.
SCREEN_ALL_FEATURES = True
NON_FEATURE_COLS = ("label", "image", "condition", "cluster", "PC1", "PC2")
ALPHA = 0.05
# ──────────────────────────────────────────────────────────────


def load_data():
    if os.path.exists(INPUT_CSV):
        return pd.read_csv(INPUT_CSV), False

    print("WARNING: configured input not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    n = 120
    intensity = rng.normal(300, 40, n)
    df = pd.DataFrame({
        "label": np.arange(1, n + 1),
        "Intensity_MeanIntensity": intensity,
        "area_um2": 3.0 * intensity + rng.normal(0, 60, n),   # real correlation
        "Perimeter": rng.normal(400, 40, n),                  # noise
        "Solidity": rng.normal(0.9, 0.05, n),                 # noise
        "Eccentricity": rng.normal(0.5, 0.1, n),              # noise
    })
    return df, True


def iqr_outliers(x):
    q1, q3 = np.percentile(x, [25, 75])
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return int(((x < lo) | (x > hi)).sum())


def correlate(x, y):
    """Return both coefficients. Neither is 'the' answer on its own."""
    pear = stats.pearsonr(x, y)
    spear = stats.spearmanr(x, y)
    return (float(pear.statistic), float(pear.pvalue),
            float(spear.statistic), float(spear.pvalue))


def main():
    df, synthetic = load_data()
    for col in (TARGET_COLUMN, PRIMARY_COLUMN):
        if col not in df.columns:
            raise ValueError(
                f"VERIFICATION FAILED: column '{col}' not in {list(df.columns)}"
            )

    n_before = len(df)
    df = df.dropna(subset=[TARGET_COLUMN, PRIMARY_COLUMN])
    if len(df) < n_before:
        print(f"WARNING: dropped {n_before - len(df)} rows with NaN "
              f"(scipy would otherwise return a NaN p-value silently).")
    if len(df) < 3:
        raise ValueError(f"VERIFICATION FAILED: only {len(df)} rows — cannot correlate.")

    x = df[TARGET_COLUMN].to_numpy(dtype=float)
    y = df[PRIMARY_COLUMN].to_numpy(dtype=float)

    # Report outliers; do NOT silently remove them.
    n_out_x, n_out_y = iqr_outliers(x), iqr_outliers(y)
    print(f"IQR outliers (threshold=1.5): {TARGET_COLUMN}={n_out_x}, "
          f"{PRIMARY_COLUMN}={n_out_y} of {len(df)}")
    if n_out_x or n_out_y:
        print("  (reported, not removed — Pearson is sensitive to these; "
              "compare it against Spearman below)")

    r_p, p_p, r_s, p_s = correlate(x, y)
    print(f"\n{PRIMARY_COLUMN} vs {TARGET_COLUMN}, n={len(df)}")
    print(f"  Pearson  r={r_p:+.4f}  p={p_p:.6g}   (linear)")
    print(f"  Spearman r={r_s:+.4f}  p={p_s:.6g}   (monotonic, outlier-robust)")
    if abs(r_p - r_s) > 0.2:
        print("  WARNING: Pearson and Spearman disagree substantially — the "
              "relationship is non-linear, or outliers dominate. Prefer Spearman.")

    def stars(pv):
        return "***" if pv < .001 else "**" if pv < .01 else "*" if pv < .05 else "ns"

    out = pd.DataFrame([{
        "analysis": "correlation",
        "x_column": TARGET_COLUMN, "y_column": PRIMARY_COLUMN,
        "n": len(df),
        "pearson_r": r_p, "pearson_p": p_p, "pearson_significance": stars(p_p),
        "spearman_r": r_s, "spearman_p": p_s, "spearman_significance": stars(p_s),
        "n_outliers_x": n_out_x, "n_outliers_y": n_out_y,
        "alpha": ALPHA,
    }])

    # ── screening many features: BH correction is not optional ──
    screen = None
    if SCREEN_ALL_FEATURES:
        feature_cols = [c for c in df.columns
                        if c not in NON_FEATURE_COLS and c != TARGET_COLUMN
                        and pd.api.types.is_numeric_dtype(df[c])]
        rows = []
        for col in feature_cols:
            sub = df[[TARGET_COLUMN, col]].dropna()
            if len(sub) < 3:
                continue
            rp, pp, rs, ps = correlate(sub[TARGET_COLUMN].to_numpy(float),
                                       sub[col].to_numpy(float))
            rows.append({"feature": col, "n": len(sub),
                         "pearson_r": rp, "pearson_p": pp,
                         "spearman_r": rs, "spearman_p": ps})
        screen = pd.DataFrame(rows)
        if len(screen):
            # Benjamini-Hochberg. Screening without this manufactures findings.
            screen["pearson_p_bh"] = stats.false_discovery_control(
                screen["pearson_p"].to_numpy(), method="bh")
            screen["spearman_p_bh"] = stats.false_discovery_control(
                screen["spearman_p"].to_numpy(), method="bh")
            screen["significant_bh"] = screen["pearson_p_bh"] < ALPHA
            screen = screen.sort_values("pearson_p").reset_index(drop=True)
            screen.to_csv(SCREEN_CSV, index=False)

            n_raw = int((screen["pearson_p"] < ALPHA).sum())
            n_bh = int(screen["significant_bh"].sum())
            print(f"\nscreened {len(screen)} features against {TARGET_COLUMN}")
            print(f"  raw p<{ALPHA}:      {n_raw}")
            print(f"  BH-adjusted p<{ALPHA}: {n_bh}")
            if n_raw > n_bh:
                print(f"  -> {n_raw - n_bh} apparent hit(s) did not survive correction. "
                      f"Report the ADJUSTED values.")
            out["n_features_screened"] = len(screen)
            out["n_significant_raw"] = n_raw
            out["n_significant_bh"] = n_bh

    out.to_csv(OUTPUT_CSV, index=False)

    # ── verification: definitional invariants only ──
    for name, val in (("pearson_r", r_p), ("spearman_r", r_s)):
        if not np.isnan(val) and not (-1.0000001 <= val <= 1.0000001):
            raise ValueError(f"VERIFICATION FAILED: {name}={val} outside [-1,1]")
    for name, val in (("pearson_p", p_p), ("spearman_p", p_s)):
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"VERIFICATION FAILED: {name}={val} outside [0,1]")
    if screen is not None and len(screen):
        # BH-adjusted p can never be smaller than the raw p.
        if (screen["pearson_p_bh"] + 1e-9 < screen["pearson_p"]).any():
            raise ValueError("VERIFICATION FAILED: BH-adjusted p < raw p")
        if not os.path.exists(SCREEN_CSV) or os.path.getsize(SCREEN_CSV) == 0:
            raise ValueError(f"VERIFICATION FAILED: {SCREEN_CSV} missing or empty")
    if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0:
        raise ValueError(f"VERIFICATION FAILED: {OUTPUT_CSV} missing or empty")

    # A NaN correlation is legitimate for a constant column — report it.
    if np.isnan(r_p):
        print("WARNING: Pearson r is NaN — one variable is constant. That is a real "
              "property of the data, not an error.")
    if p_p >= ALPHA:
        print(f"WARNING: p={p_p:.4g} >= alpha — no detectable correlation. "
              f"A legitimate finding; report it as 'ns'.")

    print(f"\nwrote {OUTPUT_CSV}"
          + (f" and {SCREEN_CSV}" if screen is not None and len(screen) else "")
          + (" [SYNTHETIC DATA]" if synthetic else ""))
    print("Next: the plotting stage reads this CSV. Do not plot here.")


if __name__ == "__main__":
    main()
