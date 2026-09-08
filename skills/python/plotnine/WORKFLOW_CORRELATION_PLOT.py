"""
WORKFLOW: Statistics_Results.csv + raw data -> publication correlation plot (plotnine)  (STAGE 2)

Runs in the MAIN env. THIS SCRIPT PERFORMS NO STATISTICS. The r and p it prints in the
annotation are READ from Statistics_Results.csv (written by the correlation statistics stage).
The geom_smooth line is a VISUAL trend only; the reported numbers come from the CSV.

Grammar-of-graphics via plotnine 0.15.7. What this gets right:
  * geom_smooth(method="lm") draws a fit WITH a confidence band (statsmodels). If the stats
    stage found Pearson and Spearman disagree (a non-linear / outlier-driven relationship), it
    switches to method="loess" (curved, scikit-misc) — also with a band. method="lowess" is
    avoided because it draws NO band and warns.
  * save(verbose=False) so the "Saving W x H image" PlotnineWarning does not hit stderr.

NOTE ON IMPORTS: pd/np are pre-imported when run via the Supervisor; the explicit imports are
redundant there but harmless and let you run this file directly.
"""
import os

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
from plotnine import (ggplot, aes, geom_point, geom_smooth, annotate, labs,
                      theme_matplotlib, theme, element_text)

# ─────────────────────────── CONFIG ───────────────────────────
STATS_CSV = "Statistics_Results.csv"
RAW_CSV = "/app/data/Measurements.csv"
FIGURE_DIR = "figures"
FIGURE_STEM = "correlation_plotnine"

X_COLUMN = "Intensity_MeanIntensity"    # falls back to stats CSV's x_column if present
Y_COLUMN = "area_um2"                    # falls back to stats CSV's y_column if present
X_LABEL = "Mean intensity (a.u.)"
Y_LABEL = "Cell Area (μm²)"
TITLE = "Area vs intensity"
POINT_COLOR = "#333333"
FIT_COLOR = "#0173b2"                    # colourblind blue
DISAGREE_THRESHOLD = 0.2                 # |pearson_r - spearman_r| above this -> loess
# ──────────────────────────────────────────────────────────────


def load_inputs():
    if os.path.exists(STATS_CSV) and os.path.exists(RAW_CSV):
        return pd.read_csv(STATS_CSV), pd.read_csv(RAW_CSV), False

    print("WARNING: inputs not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    n = 120
    x = rng.normal(300, 40, n)
    y = 3.0 * x + rng.normal(0, 60, n)
    raw = pd.DataFrame({X_COLUMN: x, Y_COLUMN: y})
    r_p = float(np.corrcoef(x, y)[0, 1])
    stats_row = pd.DataFrame([{
        "analysis": "correlation", "x_column": X_COLUMN, "y_column": Y_COLUMN, "n": n,
        "pearson_r": r_p, "pearson_p": 1e-20, "pearson_significance": "***",
        "spearman_r": r_p - 0.01, "spearman_p": 1e-19, "spearman_significance": "***",
    }])
    return stats_row, raw, True


def stars(pv):
    return "***" if pv < .001 else "**" if pv < .01 else "*" if pv < .05 else "ns"


def main():
    stats_df, raw, synthetic = load_inputs()
    row = stats_df.iloc[0]

    # Prefer the exact columns the statistics stage correlated, if it recorded them.
    xcol = str(row["x_column"]) if "x_column" in stats_df.columns else X_COLUMN
    ycol = str(row["y_column"]) if "y_column" in stats_df.columns else Y_COLUMN
    for col in (xcol, ycol):
        if col not in raw.columns:
            raise ValueError(f"VERIFICATION FAILED: '{col}' not in raw data {list(raw.columns)}")
    if "pearson_r" not in stats_df.columns or "pearson_p" not in stats_df.columns:
        raise ValueError(f"VERIFICATION FAILED: pearson_r/pearson_p not in {STATS_CSV}. "
                         f"The statistics stage must write them; do NOT recompute here.")

    plot_df = raw[[xcol, ycol]].dropna().copy()
    if len(plot_df) < 3:
        raise ValueError(f"VERIFICATION FAILED: only {len(plot_df)} complete rows — cannot plot.")

    r_p = float(row["pearson_r"])
    p_p = float(row["pearson_p"])
    r_s = float(row["spearman_r"]) if "spearman_r" in stats_df.columns else r_p
    p_s = float(row["spearman_p"]) if "spearman_p" in stats_df.columns else p_p

    # Choose the fit to DRAW from what the stats stage already decided about linearity.
    method = "loess" if abs(r_p - r_s) > DISAGREE_THRESHOLD else "lm"
    if method == "loess":
        print(f"Pearson r={r_p:+.3f} and Spearman r={r_s:+.3f} disagree "
              f"(>|{DISAGREE_THRESHOLD}|) — drawing a LOESS curve instead of a line.")

    # Annotation text uses the r,p READ FROM THE CSV — never recomputed here.
    label = (f"Pearson r = {r_p:+.2f} ({stars(p_p)})\n"
             f"Spearman r = {r_s:+.2f} ({stars(p_s)})\n"
             f"n = {len(plot_df)}")
    x_lo, x_hi = plot_df[xcol].min(), plot_df[xcol].max()
    y_lo, y_hi = plot_df[ycol].min(), plot_df[ycol].max()
    ax = x_lo + 0.04 * (x_hi - x_lo)     # annotation anchor: top-left, inside the axes
    ay = y_hi - 0.02 * (y_hi - y_lo)

    os.makedirs(FIGURE_DIR, exist_ok=True)
    p = (ggplot(plot_df, aes(x=xcol, y=ycol))
         + geom_point(color=POINT_COLOR, alpha=0.6, size=1.8)
         + geom_smooth(method=method, se=True, color=FIT_COLOR, fill=FIT_COLOR, alpha=0.2)
         + annotate("text", x=ax, y=ay, label=label, ha="left", va="top", size=11)
         + labs(title=TITLE, x=X_LABEL, y=Y_LABEL)
         + theme_matplotlib()
         + theme(figure_size=(6.5, 6), axis_title=element_text(size=14),
                 axis_text=element_text(size=12), plot_title=element_text(size=16)))

    png = os.path.join(FIGURE_DIR, f"{FIGURE_STEM}.png")
    svg = os.path.join(FIGURE_DIR, f"{FIGURE_STEM}.svg")
    p.save(png, dpi=300, width=6.5, height=6, verbose=False)
    p.save(svg, width=6.5, height=6, verbose=False)

    # ── verification: invariants only ──
    for name, val in (("pearson_r", r_p), ("spearman_r", r_s)):
        if not np.isnan(val) and not (-1.0000001 <= val <= 1.0000001):
            raise ValueError(f"VERIFICATION FAILED: {name}={val} outside [-1,1]")
    if not (0.0 <= p_p <= 1.0):
        raise ValueError(f"VERIFICATION FAILED: pearson_p {p_p} outside [0,1]")
    for path in (png, svg):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise ValueError(f"VERIFICATION FAILED: {path} missing or empty")

    if p_p >= 0.05:
        print("WARNING: correlation is not significant (p>=0.05). Reporting 'ns' is a "
              "legitimate result — do not fish for a different coefficient.")

    print(f"wrote {png} (300 dpi) and {svg} — {len(plot_df)} points, {method} fit, "
          f"r/p read from {STATS_CSV}" + (" [SYNTHETIC DATA]" if synthetic else ""))


if __name__ == "__main__":
    main()
