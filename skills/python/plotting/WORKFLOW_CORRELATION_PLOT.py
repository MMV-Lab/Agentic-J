"""
WORKFLOW: Statistics_Results.csv + raw data -> publication correlation figure  (STAGE 2)

Runs in the MAIN env. THIS SCRIPT PERFORMS NO STATISTICS. The r and p it annotates are
READ from Statistics_Results.csv. If you recompute them here, the figure and the text
can silently disagree.

Chooses the coefficient the statistics stage justified: if Pearson and Spearman
disagreed there, the honest annotation is Spearman (monotonic, outlier-robust).

NOTE ON IMPORTS: when the Supervisor executes this via execute_script, pd/np/plt/sns are
already in scope. The explicit imports are redundant there but harmless, and let you run
this file directly.
"""
import os

import matplotlib
matplotlib.use("Agg")           # headless container
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# ─────────────────────────── CONFIG ───────────────────────────
STATS_CSV = "Statistics_Results.csv"
RAW_CSV = "/app/data/Measurements.csv"
FIGURE_DIR = "figures"
FIGURE_STEM = "correlation"

X_COLUMN = "Intensity_MeanIntensity"
Y_COLUMN = "area_um2"
X_LABEL = "Mean Intensity (a.u.)"       # ALWAYS carry the unit
Y_LABEL = "Cell Area (μm²)"
TITLE = "Cell area vs. mean intensity"
# ──────────────────────────────────────────────────────────────

plt.rcParams.update({
    "font.size": 12, "axes.labelsize": 14, "axes.titlesize": 16,
    "legend.fontsize": 12, "axes.linewidth": 1.0, "lines.linewidth": 2.0,
})
sns.set_theme(style="whitegrid")
sns.set_palette("colorblind")           # not palette= on the call (0.13 deprecation)
BLUE = sns.color_palette("colorblind")[0]    # #0173b2


def load_inputs():
    if os.path.exists(STATS_CSV) and os.path.exists(RAW_CSV):
        return pd.read_csv(STATS_CSV), pd.read_csv(RAW_CSV), False

    print("WARNING: inputs not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    intensity = rng.normal(300, 40, 120)
    raw = pd.DataFrame({
        X_COLUMN: intensity,
        Y_COLUMN: 3.0 * intensity + rng.normal(0, 60, 120),
    })
    stats_row = pd.DataFrame([{
        "x_column": X_COLUMN, "y_column": Y_COLUMN, "n": 120,
        "pearson_r": 0.8687, "pearson_p": 8.48e-38, "pearson_significance": "***",
        "spearman_r": 0.8594, "spearman_p": 3.53e-36, "spearman_significance": "***",
        "n_outliers_x": 0, "n_outliers_y": 1,
    }])
    return stats_row, raw, True


def main():
    stats_df, raw, synthetic = load_inputs()

    for col in (X_COLUMN, Y_COLUMN):
        if col not in raw.columns:
            raise ValueError(f"VERIFICATION FAILED: '{col}' not in raw data "
                             f"{list(raw.columns)}")
    required = ("pearson_r", "pearson_p", "spearman_r", "spearman_p")
    missing = [c for c in required if c not in stats_df.columns]
    if missing:
        raise ValueError(f"VERIFICATION FAILED: {missing} not in {STATS_CSV}. "
                         f"The statistics stage must write them; do NOT recompute here.")

    row = stats_df.iloc[0]
    r_p, p_p = float(row["pearson_r"]), float(row["pearson_p"])
    r_s, p_s = float(row["spearman_r"]), float(row["spearman_p"])

    # If the two coefficients disagreed, the statistics stage already flagged a
    # non-linear or outlier-driven relationship. Annotate the robust one.
    if abs(r_p - r_s) > 0.2:
        coef_name, r, p = "Spearman ρ", r_s, p_s
        print(f"Pearson ({r_p:.3f}) and Spearman ({r_s:.3f}) disagree — annotating "
              f"Spearman, and drawing a LOWESS fit rather than a straight line.")
        lowess = True
    else:
        coef_name, r, p = "Pearson r", r_p, p_p
        lowess = False
    print(f"read from {STATS_CSV}: {coef_name}={r:.4f}, p={p:.4g}")

    data = raw[[X_COLUMN, Y_COLUMN]].dropna()
    if len(data) < 3:
        raise ValueError(f"VERIFICATION FAILED: only {len(data)} complete rows.")
    if len(data) < len(raw):
        print(f"WARNING: dropped {len(raw) - len(data)} rows with NaN.")

    os.makedirs(FIGURE_DIR, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.5, 6))

    sns.regplot(
        data=data, x=X_COLUMN, y=Y_COLUMN, ax=ax,
        lowess=lowess,
        # NOTE: use "linewidths" (plural) here. matplotlib's scatter treats
        # `linewidth` and `linewidths` as aliases and raises TypeError if seaborn
        # passes both -> "Got both 'linewidth' and 'linewidths'".
        scatter_kws={"s": 28, "alpha": 0.6, "color": BLUE,
                     "edgecolors": "white", "linewidths": 0.5},
        line_kws={"color": "black", "linewidth": 2.0},
        # marker shape carries information in grayscale, not just colour
        marker="o",
    )

    def stars(pv):
        return "***" if pv < .001 else "**" if pv < .01 else "*" if pv < .05 else "ns"

    annotation = (f"{coef_name} = {r:.3f}\n"
                  f"p = {p:.2e} ({stars(p)})\n"
                  f"n = {len(data)}")
    ax.text(0.03, 0.97, annotation, transform=ax.transAxes,
            va="top", ha="left", fontsize=12,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      edgecolor="0.7", alpha=0.9))

    ax.set_xlabel(X_LABEL)
    ax.set_ylabel(Y_LABEL)
    ax.set_title(TITLE)

    png = os.path.join(FIGURE_DIR, f"{FIGURE_STEM}.png")
    svg = os.path.join(FIGURE_DIR, f"{FIGURE_STEM}.svg")
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    plt.close(fig)

    # ── verification: invariants ──
    if not (-1.0000001 <= r <= 1.0000001):
        raise ValueError(f"VERIFICATION FAILED: coefficient {r} outside [-1,1]")
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"VERIFICATION FAILED: p {p} outside [0,1]")
    for path in (png, svg):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise ValueError(f"VERIFICATION FAILED: {path} missing or empty")

    n_out = int(row.get("n_outliers_x", 0)) + int(row.get("n_outliers_y", 0))
    if n_out:
        print(f"WARNING: {n_out} IQR outliers were reported by the statistics stage. "
              f"They are drawn (not hidden). Mention them in the caption.")
    if stars(p) == "ns":
        print("WARNING: correlation is not significant. Annotating 'ns' is correct.")

    print(f"wrote {png} (300 dpi) and {svg}"
          + (" [SYNTHETIC DATA]" if synthetic else ""))


if __name__ == "__main__":
    main()
