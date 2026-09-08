"""
WORKFLOW: Statistics_Results.csv + raw data -> publication boxplot  (STAGE 2)

Runs in the MAIN env. THIS SCRIPT PERFORMS NO STATISTICS. Every number it draws
(p-value, significance stars, N) is READ from Statistics_Results.csv, which the
statistics stage wrote. Recomputing here would let the figure disagree with the text.

TWO TRAPS THIS AVOIDS:
  1. sns.swarmplot SILENTLY DROPS POINTS that do not fit ("17.4% of the points cannot
     be placed"), while pretending to show all raw data. This script detects the
     warning and falls back to stripplot, which never drops points.
  2. Passing `palette=` without `hue=` is deprecated in seaborn 0.13 and breaks in
     0.14. We call sns.set_palette() once instead.

NOTE ON IMPORTS: when the Supervisor executes this via execute_script, pd/np/plt/sns are
already in scope and the Agg backend is fine. The explicit imports are redundant there
but harmless, and let you run this file directly.
"""
import os
import warnings

import matplotlib
matplotlib.use("Agg")            # headless container: no display
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# ─────────────────────────── CONFIG ───────────────────────────
STATS_CSV = "Statistics_Results.csv"        # written by the statistics stage
RAW_CSV = "/app/data/Measurements.csv"      # the per-object values to draw
FIGURE_DIR = "figures"
FIGURE_STEM = "group_comparison"

VALUE_COLUMN = "area_um2"
GROUP_COLUMN = "condition"
Y_LABEL = "Cell Area (μm²)"                 # ALWAYS carry the unit
TITLE = "Cell area by condition"
MAX_SWARM_POINTS = 300                      # above this, stripplot outright
# ──────────────────────────────────────────────────────────────

plt.rcParams.update({
    "font.size": 12,          # tick labels   (>= 12pt)
    "axes.labelsize": 14,     # axis labels   (>= 14pt)
    "axes.titlesize": 16,     # title         (>= 16pt)
    "legend.fontsize": 12,
    "axes.linewidth": 1.0,    # axis lines    (>= 1.0pt)
    "lines.linewidth": 2.0,   # plot lines    (>= 1.5pt)
})
sns.set_theme(style="whitegrid")
sns.set_palette("colorblind")   # NOT palette= on the call: deprecated without hue=


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
        "n1": 60, "n2": 60,
        "mean1": 850.0, "mean2": 970.0,
        "test": "Welch t-test", "statistic": -7.1,
        "p_value": 8.4e-11, "significance": "***",
        "effect_size_name": "cohens_d", "effect_size": 1.30,
    }])
    return stats_row, raw, True


def sig_bracket(ax, x1, x2, y, h, text, lw=1.5, fontsize=12):
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], lw=lw, c="black")
    ax.text((x1 + x2) / 2, y + h, text, ha="center", va="bottom", fontsize=fontsize)


def draw_points(ax, data, order):
    """swarmplot if it can place every point, else stripplot. Never drop data."""
    n = len(data)
    if n > MAX_SWARM_POINTS:
        print(f"{n} points > {MAX_SWARM_POINTS} — using stripplot (swarm would drop points).")
        sns.stripplot(data=data, x=GROUP_COLUMN, y=VALUE_COLUMN, order=order,
                      ax=ax, color=".25", size=3, jitter=0.25, alpha=0.6)
        return "stripplot"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sns.swarmplot(data=data, x=GROUP_COLUMN, y=VALUE_COLUMN, order=order,
                      ax=ax, color=".25", size=3)
        dropped = [w for w in caught if "cannot be placed" in str(w.message)]

    if dropped:
        # seaborn already drew a swarm missing points. Redraw honestly.
        print(f"swarmplot dropped points ({str(dropped[0].message)[:60]}...) "
              f"-> redrawing as stripplot")
        ax.clear()
        sns.boxplot(data=data, x=GROUP_COLUMN, y=VALUE_COLUMN, order=order, ax=ax,
                    hue=GROUP_COLUMN, legend=False, showfliers=False, width=0.6)
        sns.stripplot(data=data, x=GROUP_COLUMN, y=VALUE_COLUMN, order=order,
                      ax=ax, color=".25", size=3, jitter=0.25, alpha=0.6)
        return "stripplot"
    return "swarmplot"


def main():
    stats_df, raw, synthetic = load_inputs()

    for col in (VALUE_COLUMN, GROUP_COLUMN):
        if col not in raw.columns:
            raise ValueError(f"VERIFICATION FAILED: '{col}' not in raw data "
                             f"{list(raw.columns)}")
    for col in ("p_value", "significance"):
        if col not in stats_df.columns:
            raise ValueError(f"VERIFICATION FAILED: '{col}' not in {STATS_CSV}. "
                             f"The statistics stage must write it; do NOT recompute here.")

    row = stats_df.iloc[0]
    p_value = float(row["p_value"])
    stars = str(row["significance"])
    print(f"read from {STATS_CSV}: p={p_value:.4g} ({stars}), test={row.get('test','?')}")

    order = [row["group1"], row["group2"]] if "group1" in stats_df.columns \
        else sorted(raw[GROUP_COLUMN].unique())
    plot_df = raw[raw[GROUP_COLUMN].isin(order)].dropna(subset=[VALUE_COLUMN])
    if plot_df.empty:
        raise ValueError("VERIFICATION FAILED: nothing to plot after filtering.")

    os.makedirs(FIGURE_DIR, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6))

    # hue=+legend=False keeps the colorblind palette without the 0.13 deprecation
    sns.boxplot(data=plot_df, x=GROUP_COLUMN, y=VALUE_COLUMN, order=order, ax=ax,
                hue=GROUP_COLUMN, legend=False, showfliers=False, width=0.6)
    kind = draw_points(ax, plot_df, order)

    # significance bracket, using the p-value the STATISTICS stage computed
    vals = plot_df[VALUE_COLUMN]
    top, span = vals.max(), vals.max() - vals.min()
    sig_bracket(ax, 0, 1, top + 0.05 * span, 0.02 * span, stars)
    ax.set_ylim(top=top + 0.18 * span)     # make room or the bracket is clipped

    ax.set_xlabel(GROUP_COLUMN.capitalize())
    ax.set_ylabel(Y_LABEL)
    ax.set_title(TITLE)

    n_by_group = plot_df.groupby(GROUP_COLUMN)[VALUE_COLUMN].size()
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([f"{g}\n(n={n_by_group[g]})" for g in order])

    png = os.path.join(FIGURE_DIR, f"{FIGURE_STEM}.png")
    svg = os.path.join(FIGURE_DIR, f"{FIGURE_STEM}.svg")
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    plt.close(fig)

    # ── verification: invariants ──
    if not (0.0 <= p_value <= 1.0):
        raise ValueError(f"VERIFICATION FAILED: p_value {p_value} outside [0,1]")
    for path in (png, svg):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise ValueError(f"VERIFICATION FAILED: {path} missing or empty")
    if len(order) != plot_df[GROUP_COLUMN].nunique():
        raise ValueError("VERIFICATION FAILED: plotted groups != groups in data")

    if stars == "ns":
        print("WARNING: result is not significant. The 'ns' annotation is correct and "
              "the figure is publishable — do not hunt for a different test.")

    print(f"wrote {png} (300 dpi) and {svg} — raw points drawn with {kind}"
          + (" [SYNTHETIC DATA]" if synthetic else ""))


if __name__ == "__main__":
    main()
