"""
WORKFLOW: Statistics_Results.csv + raw data -> publication boxplot (plotnine)  (STAGE 2)

Runs in the MAIN env. THIS SCRIPT PERFORMS NO STATISTICS. Every number it draws (p-value,
significance stars, N) is READ from Statistics_Results.csv, which the statistics stage wrote.
Recomputing here would let the figure disagree with the text.

Grammar-of-graphics via plotnine 0.15.7. Three plotnine specifics this gets right:
  1. save(verbose=False) — the DEFAULT verbose=True prints a "Saving W x H image"
     PlotnineWarning to stderr.
  2. Discrete x positions are 1-BASED (first category is x=1). An ordered pd.Categorical fixes
     the order, and the significance bracket is placed at the 1-based positions of the two
     compared groups.
  3. geom_jitter overlays EVERY raw point (seaborn's swarmplot silently drops points that do
     not fit; plotnine's jitter/sina never do).

NOTE ON IMPORTS: when the Supervisor executes this via execute_script, pd/np are already in
scope. The explicit imports are redundant there but harmless, and let you run this file directly.
"""
import os

import matplotlib
matplotlib.use("Agg")            # headless container: no display
import numpy as np
import pandas as pd
from plotnine import (ggplot, aes, geom_boxplot, geom_jitter, annotate,
                      scale_fill_manual, scale_x_discrete, labs, theme_matplotlib,
                      theme, element_text, expand_limits)

# ─────────────────────────── CONFIG ───────────────────────────
STATS_CSV = "Statistics_Results.csv"        # written by the statistics stage
RAW_CSV = "/app/data/Measurements.csv"      # the per-object values to draw
FIGURE_DIR = "figures"
FIGURE_STEM = "group_comparison_plotnine"

VALUE_COLUMN = "area_um2"
GROUP_COLUMN = "condition"
Y_LABEL = "Cell Area (μm²)"                 # ALWAYS carry the unit
X_LABEL = "Condition"
TITLE = "Cell area by condition"
# Colourblind-safe hex (blue, orange, green, vermilion, purple). plotnine has no built-in
# 'colorblind' palette, so we map it explicitly with scale_fill_manual.
CB = ["#0173b2", "#de8f05", "#029e73", "#d55e00", "#cc78bc"]
# ──────────────────────────────────────────────────────────────


def load_inputs():
    if os.path.exists(STATS_CSV) and os.path.exists(RAW_CSV):
        return pd.read_csv(STATS_CSV), pd.read_csv(RAW_CSV), False

    print("WARNING: inputs not found — running on synthetic data.")
    rng = np.random.default_rng(0)
    raw = pd.DataFrame({
        GROUP_COLUMN: ["control"] * 60 + ["treated"] * 60,
        VALUE_COLUMN: np.r_[rng.normal(850, 90, 60), rng.normal(970, 95, 60)],
    })
    stats_row = pd.DataFrame([{
        "group1": "control", "group2": "treated",
        "n1": 60, "n2": 60, "mean1": 850.0, "mean2": 970.0,
        "test": "Welch t-test", "statistic": -7.1,
        "p_value": 8.4e-11, "significance": "***",
        "effect_size_name": "cohens_d", "effect_size": 1.30,
    }])
    return stats_row, raw, True


def sig_bracket(x1, x2, y, h, text, size=12):
    """plotnine layers for a significance bracket x1..x2 at height y (tick height h). x
    positions are 1-BASED on the discrete axis."""
    return [
        annotate("segment", x=x1, xend=x1, y=y - h, yend=y),      # left tick
        annotate("segment", x=x1, xend=x2, y=y, yend=y),          # top bar
        annotate("segment", x=x2, xend=x2, y=y, yend=y - h),      # right tick
        annotate("text", x=(x1 + x2) / 2.0, y=y + h, label=text, size=size, va="bottom"),
    ]


def main():
    stats_df, raw, synthetic = load_inputs()

    for col in (VALUE_COLUMN, GROUP_COLUMN):
        if col not in raw.columns:
            raise ValueError(f"VERIFICATION FAILED: '{col}' not in raw data {list(raw.columns)}")
    for col in ("p_value", "significance"):
        if col not in stats_df.columns:
            raise ValueError(f"VERIFICATION FAILED: '{col}' not in {STATS_CSV}. The statistics "
                             f"stage must write it; do NOT recompute here.")

    row = stats_df.iloc[0]
    p_value = float(row["p_value"])
    stars = str(row["significance"])
    g1 = row["group1"] if "group1" in stats_df.columns else None
    g2 = row["group2"] if "group2" in stats_df.columns else None
    print(f"read from {STATS_CSV}: p={p_value:.4g} ({stars}), test={row.get('test', '?')}")

    order = [g1, g2] if g1 is not None else sorted(raw[GROUP_COLUMN].unique())
    plot_df = raw[raw[GROUP_COLUMN].isin(order)].dropna(subset=[VALUE_COLUMN]).copy()
    if plot_df.empty:
        raise ValueError("VERIFICATION FAILED: nothing to plot after filtering.")

    # Ordered categorical => deterministic, 1-based positions on the discrete x axis.
    plot_df[GROUP_COLUMN] = pd.Categorical(plot_df[GROUP_COLUMN], categories=order, ordered=True)
    pos = {g: i + 1 for i, g in enumerate(order)}          # 1-BASED lookup
    n_by_group = plot_df.groupby(GROUP_COLUMN, observed=True)[VALUE_COLUMN].size()
    x_labels = [f"{g}\n(n={int(n_by_group[g])})" for g in order]

    vals = plot_df[VALUE_COLUMN]
    top, span = float(vals.max()), float(vals.max() - vals.min())
    y_bar, h = top + 0.05 * span, 0.03 * span

    os.makedirs(FIGURE_DIR, exist_ok=True)
    p = (ggplot(plot_df, aes(x=GROUP_COLUMN, y=VALUE_COLUMN))
         + geom_boxplot(aes(fill=GROUP_COLUMN), width=0.6, outlier_alpha=0, show_legend=False)
         + geom_jitter(width=0.2, height=0, alpha=0.5, size=1.2, color="#333333")
         + scale_fill_manual(values=CB[:len(order)])
         + scale_x_discrete(limits=order, labels=x_labels)
         + labs(title=TITLE, x=X_LABEL, y=Y_LABEL)
         + theme_matplotlib()
         + theme(figure_size=(6, 6), axis_title=element_text(size=14),
                 axis_text=element_text(size=12), plot_title=element_text(size=16))
         + expand_limits(y=top + 0.20 * span))       # headroom so the bracket is not clipped

    # significance bracket, using the p-value the STATISTICS stage computed
    if g1 is not None and g2 is not None:
        for layer in sig_bracket(pos[g1], pos[g2], y_bar, h, stars):
            p = p + layer

    png = os.path.join(FIGURE_DIR, f"{FIGURE_STEM}.png")
    svg = os.path.join(FIGURE_DIR, f"{FIGURE_STEM}.svg")
    p.save(png, dpi=300, width=6, height=6, verbose=False)   # verbose=False: no stderr noise
    p.save(svg, width=6, height=6, verbose=False)

    # ── verification: invariants only ──
    if not (0.0 <= p_value <= 1.0):
        raise ValueError(f"VERIFICATION FAILED: p_value {p_value} outside [0,1]")
    for path in (png, svg):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise ValueError(f"VERIFICATION FAILED: {path} missing or empty")
    if plot_df[GROUP_COLUMN].nunique() != len(order):
        raise ValueError("VERIFICATION FAILED: plotted groups != groups in data")

    if stars == "ns":
        print("WARNING: result is not significant. The 'ns' annotation is correct and the "
              "figure is publishable — do not hunt for a different test.")

    print(f"wrote {png} (300 dpi) and {svg} — {len(plot_df)} raw points drawn with geom_jitter"
          + (" [SYNTHETIC DATA]" if synthetic else ""))


if __name__ == "__main__":
    main()
