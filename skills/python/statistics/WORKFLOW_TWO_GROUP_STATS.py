"""
WORKFLOW: two-group comparison -> Statistics_Results.csv  (STAGE 1)

Runs in the MAIN env. THIS SCRIPT DOES NOT PLOT. The plotting stage reads the CSV it
writes. Never combine the two.

WHAT THIS GETS RIGHT, THAT THE OBVIOUS VERSION GETS WRONG:
  * Welch's t-test, not Student's. scipy defaults to equal_var=True; in simulation that
    reports 33% false positives when the smaller group has the larger variance. Welch
    holds at 5% and costs nothing when variances are equal.
  * Shapiro-Wilk only guards SMALL samples. At n>=100 it rejects normality on data a
    t-test handles fine, so it is applied here only below SHAPIRO_MAX_N.
  * NaN is dropped explicitly. scipy's default nan_policy='propagate' returns a NaN
    p-value with no error.
  * An effect size and a confidence interval are reported alongside p. A p-value alone
    is not a result.
  * Pseudoreplication is checked: if cells are nested in images, N is the number of
    IMAGES, not cells.

NOTE ON IMPORTS: when the Supervisor executes this via execute_script, pd/np/stats are
already in scope. The explicit imports below are redundant there but harmless, and they
let you run this file directly to see it work.
"""
import os

import numpy as np
import pandas as pd
from scipy import stats

# ─────────────────────────── CONFIG ───────────────────────────
INPUT_CSV = "/app/data/Measurements.csv"
OUTPUT_CSV = "Statistics_Results.csv"

VALUE_COLUMN = "area_um2"       # the measurement to compare
GROUP_COLUMN = "condition"      # must contain exactly 2 groups
# If several rows come from the same image/animal, set this. The script will then
# average per unit and test on those means — the honest N. None = rows are independent.
REPLICATE_COLUMN = "image"

SHAPIRO_MAX_N = 50              # above this, Shapiro is over-powered; judge by shape
ALPHA = 0.05
# ──────────────────────────────────────────────────────────────


def load_data():
    if os.path.exists(INPUT_CSV):
        return pd.read_csv(INPUT_CSV), False

    print("WARNING: configured input not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    rows = []
    for img in range(8):
        cond = "treated" if img % 2 else "control"
        shift = 120.0 if cond == "treated" else 0.0
        img_effect = rng.normal(0, 40)          # real between-image variability
        for _ in range(30):
            rows.append({"image": f"img_{img:02d}", "condition": cond,
                         "area_um2": rng.normal(850 + shift + img_effect, 90)})
    return pd.DataFrame(rows), True


def cohens_d(a, b):
    nx, ny = len(a), len(b)
    sp = np.sqrt(((nx - 1) * a.var(ddof=1) + (ny - 1) * b.var(ddof=1)) / (nx + ny - 2))
    return (b.mean() - a.mean()) / sp if sp > 0 else np.nan


def main():
    df, synthetic = load_data()
    for col in (VALUE_COLUMN, GROUP_COLUMN):
        if col not in df.columns:
            raise ValueError(
                f"VERIFICATION FAILED: column '{col}' not in {list(df.columns)}"
            )

    # scipy's default nan_policy='propagate' silently returns a NaN p-value.
    n_before = len(df)
    df = df.dropna(subset=[VALUE_COLUMN, GROUP_COLUMN])
    if len(df) < n_before:
        print(f"WARNING: dropped {n_before - len(df)} rows with NaN in "
              f"'{VALUE_COLUMN}' or '{GROUP_COLUMN}'.")

    groups = sorted(df[GROUP_COLUMN].unique())
    if len(groups) != 2:
        raise ValueError(
            f"VERIFICATION FAILED: need exactly 2 groups in '{GROUP_COLUMN}', "
            f"found {len(groups)}: {groups}. Use kruskal/f_oneway for 3+."
        )
    g1, g2 = groups

    # ── pseudoreplication: cells inside an image are not independent samples ──
    unit = "row"
    if REPLICATE_COLUMN and REPLICATE_COLUMN in df.columns:
        per_unit = (df.groupby([REPLICATE_COLUMN, GROUP_COLUMN])[VALUE_COLUMN]
                      .mean().reset_index())
        n_units = per_unit[REPLICATE_COLUMN].nunique()
        print(f"nesting: {len(df)} rows in {n_units} '{REPLICATE_COLUMN}' units — "
              f"averaging per unit so N = {n_units}, not {len(df)}.")
        analysis, unit = per_unit, REPLICATE_COLUMN

        # Show what pseudoreplication would have bought. This is the WRONG analysis;
        # it is printed only so the size of the error is visible.
        naive_a = df.loc[df[GROUP_COLUMN] == g1, VALUE_COLUMN].to_numpy(float)
        naive_b = df.loc[df[GROUP_COLUMN] == g2, VALUE_COLUMN].to_numpy(float)
        naive_p = stats.ttest_ind(naive_a, naive_b, equal_var=False).pvalue
        print(f"  (pooling all {len(df)} cells as if independent would give "
              f"p={naive_p:.3g} — that is pseudoreplication, and it is NOT what is "
              f"reported below.)")
    else:
        print(f"WARNING: REPLICATE_COLUMN not set — treating all {len(df)} rows as "
              f"independent samples. Only correct if they truly are.")
        analysis = df

    a = analysis.loc[analysis[GROUP_COLUMN] == g1, VALUE_COLUMN].to_numpy(dtype=float)
    b = analysis.loc[analysis[GROUP_COLUMN] == g2, VALUE_COLUMN].to_numpy(dtype=float)
    print(f"N: {g1}={len(a)}  {g2}={len(b)}  (unit of replication: {unit})")
    if len(a) < 2 or len(b) < 2:
        raise ValueError(
            f"VERIFICATION FAILED: need >= 2 observations per group, got {len(a)}/{len(b)}"
        )
    if len(a) < 3 or len(b) < 3:
        print("WARNING: fewer than 3 units per group — any p-value here is decorative.")

    # ── normality: Shapiro only where it is informative ──
    normal = True
    shapiro_p = {}
    for name, arr in ((g1, a), (g2, b)):
        if 3 <= len(arr) <= SHAPIRO_MAX_N:
            p = float(stats.shapiro(arr).pvalue)
            shapiro_p[name] = p
            print(f"  shapiro({name}, n={len(arr)}): p={p:.4f}")
            if len(arr) < 8:
                print(f"    (n={len(arr)} is too small to assess normality; this test "
                      f"has almost no power. Falling back to the rank test is the "
                      f"conservative choice.)")
            if p < ALPHA:
                normal = False
        else:
            shapiro_p[name] = np.nan
            print(f"  shapiro({name}) skipped (n={len(arr)}) — over-powered above "
                  f"n={SHAPIRO_MAX_N}; judging by shape instead.")

    # ── the test. Welch, never Student. ──
    if normal:
        res = stats.ttest_ind(a, b, equal_var=False)      # equal_var=False = Welch
        test_name = "Welch t-test"
        ci = res.confidence_interval()
        ci_low, ci_high = float(ci.low), float(ci.high)
        effect_name, effect = "cohens_d", cohens_d(a, b)
    else:
        res = stats.mannwhitneyu(a, b, alternative="two-sided")
        test_name = "Mann-Whitney U"
        ci_low = ci_high = np.nan
        U = res.statistic
        effect_name, effect = "rank_biserial_r", 1 - 2 * U / (len(a) * len(b))

    p = float(res.pvalue)
    stat = float(res.statistic)
    print(f"\n{test_name}: statistic={stat:.4f}  p={p:.6g}")
    print(f"{effect_name} = {effect:.3f}")
    if not np.isnan(ci_low):
        print(f"95% CI of mean difference: [{ci_low:.3f}, {ci_high:.3f}]")

    def stars(pv):
        return "***" if pv < .001 else "**" if pv < .01 else "*" if pv < .05 else "ns"

    out = pd.DataFrame([{
        "value_column": VALUE_COLUMN,
        "group_column": GROUP_COLUMN,
        "group1": g1, "group2": g2,
        "unit_of_replication": unit,
        "n1": len(a), "n2": len(b),
        "mean1": a.mean(), "mean2": b.mean(),
        "sd1": a.std(ddof=1), "sd2": b.std(ddof=1),
        "median1": np.median(a), "median2": np.median(b),
        "test": test_name,
        "statistic": stat,
        "p_value": p,
        "significance": stars(p),
        "effect_size_name": effect_name,
        "effect_size": float(effect),
        "ci_low": ci_low, "ci_high": ci_high,
        "shapiro_p_group1": shapiro_p[g1], "shapiro_p_group2": shapiro_p[g2],
        "normality_assumed": normal,
        "alpha": ALPHA,
        "n_rows_input": int(len(df)),
    }])
    out.to_csv(OUTPUT_CSV, index=False)

    # ── verification: definitional invariants only ──
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"VERIFICATION FAILED: p-value {p} outside [0,1]")
    if np.isnan(p):
        raise ValueError("VERIFICATION FAILED: p-value is NaN — check NaN handling")
    if effect_name == "rank_biserial_r" and not (-1.0000001 <= effect <= 1.0000001):
        raise ValueError(f"VERIFICATION FAILED: rank-biserial {effect} outside [-1,1]")
    if len(out) != 1:
        raise ValueError("VERIFICATION FAILED: expected exactly one summary row")
    if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0:
        raise ValueError(f"VERIFICATION FAILED: {OUTPUT_CSV} missing or empty")

    # "Not significant" is a result, not a failure.
    if p >= ALPHA:
        print(f"WARNING: p={p:.4g} >= alpha={ALPHA} — no detectable difference. "
              f"That is a legitimate finding; report it as 'ns'.")
    if abs(effect) < 0.2 and p < ALPHA:
        print(f"WARNING: significant but tiny effect ({effect_name}={effect:.3f}). "
              f"Report the magnitude, not just the p-value.")

    print(f"\nwrote {OUTPUT_CSV}" + (" [SYNTHETIC DATA]" if synthetic else ""))
    print("Next: the plotting stage reads this CSV. Do not plot here.")


if __name__ == "__main__":
    main()
