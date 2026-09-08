"""
WORKFLOW: raw measurements -> faceted small-multiple distributions (plotnine)  (STAGE 2)

Runs in the MAIN env. THIS SCRIPT PERFORMS NO STATISTICS. It is a distribution / QC figure: one
panel per group, each showing the shape of a measurement's distribution. It needs only the raw
per-object CSV (no Statistics_Results.csv) — there is no p-value to read or annotate here.

This is plotnine's showcase: a single ggplot(...) + facet_wrap turns into a grid of comparable
panels with no loops. What it gets right:
  * geom_histogram + geom_density on a shared, colourblind-mapped fill.
  * facet_wrap(scales="free_y") so panels with different counts stay legible.
  * save(verbose=False) so the "Saving W x H image" PlotnineWarning does not reach stderr.

If the configured value/group columns are missing, it falls back to self-contained synthetic
data so the file always runs.

NOTE ON IMPORTS: pd/np are pre-imported when run via the Supervisor; the explicit imports are
redundant there but harmless and let you run this file directly.
"""
import os

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
from plotnine import (ggplot, aes, geom_histogram, geom_density, facet_wrap,
                      scale_fill_manual, scale_color_manual, labs, theme_matplotlib,
                      theme, element_text, after_stat)

# ─────────────────────────── CONFIG ───────────────────────────
RAW_CSV = "/app/data/Measurements.csv"
FIGURE_DIR = "figures"
FIGURE_STEM = "distributions_by_group_plotnine"

VALUE_COLUMN = "area_um2"
GROUP_COLUMN = "condition"       # one facet panel per level of this column
X_LABEL = "Cell Area (μm²)"
TITLE = "Area distribution by condition"
BINS = 25
FACET_NCOL = 3
CB = ["#0173b2", "#de8f05", "#029e73", "#d55e00", "#cc78bc",
      "#ca9161", "#fbafe4", "#949494", "#ece133", "#56b4e9"]
# ──────────────────────────────────────────────────────────────


def load_inputs():
    if os.path.exists(RAW_CSV):
        df = pd.read_csv(RAW_CSV)
        if VALUE_COLUMN in df.columns and GROUP_COLUMN in df.columns:
            return df, False

    print("WARNING: input not found (or missing columns) — running on synthetic data.")
    rng = np.random.default_rng(0)
    frames = []
    for i, (grp, mu, sd) in enumerate([("control", 850, 90), ("treated", 970, 95),
                                       ("washout", 900, 110)]):
        frames.append(pd.DataFrame({GROUP_COLUMN: grp,
                                    VALUE_COLUMN: rng.normal(mu, sd, 200)}))
    return pd.concat(frames, ignore_index=True), True


def main():
    df, synthetic = load_inputs()
    for col in (VALUE_COLUMN, GROUP_COLUMN):
        if col not in df.columns:
            raise ValueError(f"VERIFICATION FAILED: '{col}' not in data {list(df.columns)}")

    plot_df = df.dropna(subset=[VALUE_COLUMN, GROUP_COLUMN]).copy()
    if plot_df.empty:
        raise ValueError("VERIFICATION FAILED: nothing to plot after dropping NaN.")

    groups = sorted(plot_df[GROUP_COLUMN].unique())
    plot_df[GROUP_COLUMN] = pd.Categorical(plot_df[GROUP_COLUMN], categories=groups, ordered=True)
    if len(groups) > len(CB):
        raise ValueError(f"VERIFICATION FAILED: {len(groups)} groups exceeds the {len(CB)}-colour "
                         f"palette; aggregate groups or extend CB.")

    os.makedirs(FIGURE_DIR, exist_ok=True)
    # Histogram (count) with a density curve overlaid on the same y-scale via after_stat.
    p = (ggplot(plot_df, aes(x=VALUE_COLUMN, fill=GROUP_COLUMN, color=GROUP_COLUMN))
         + geom_histogram(aes(y=after_stat("density")), bins=BINS, alpha=0.45,
                          show_legend=False)
         + geom_density(alpha=0.0, size=1.0, show_legend=False)
         + facet_wrap(GROUP_COLUMN, ncol=FACET_NCOL, scales="free_y")
         + scale_fill_manual(values=CB[:len(groups)])
         + scale_color_manual(values=CB[:len(groups)])
         + labs(title=TITLE, x=X_LABEL, y="Density")
         + theme_matplotlib()
         + theme(figure_size=(4.0 * min(len(groups), FACET_NCOL), 3.6),
                 axis_title=element_text(size=14), axis_text=element_text(size=12),
                 plot_title=element_text(size=16), strip_text=element_text(size=12)))

    png = os.path.join(FIGURE_DIR, f"{FIGURE_STEM}.png")
    svg = os.path.join(FIGURE_DIR, f"{FIGURE_STEM}.svg")
    p.save(png, dpi=300, verbose=False)
    p.save(svg, verbose=False)

    # ── verification: invariants only ──
    for path in (png, svg):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise ValueError(f"VERIFICATION FAILED: {path} missing or empty")

    tiny = [g for g in groups if int((plot_df[GROUP_COLUMN] == g).sum()) < 10]
    if tiny:
        print(f"WARNING: groups with <10 observations ({tiny}) — their density curve is "
              f"unreliable; report the histogram, not the smoothed shape.")

    print(f"wrote {png} (300 dpi) and {svg} — {len(groups)} facet panels "
          f"({', '.join(groups)})" + (" [SYNTHETIC DATA]" if synthetic else ""))


if __name__ == "__main__":
    main()
