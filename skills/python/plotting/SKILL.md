---
name: plotting
description: >-
  Publication-quality plotting standards for matplotlib/seaborn figures (STAGE 2: PUBLICATION
  PLOTTING). Covers 300 DPI + dual PNG/SVG export, colorblind-safe palettes (verified: seaborn
  'colorblind' is exactly #0173b2 blue, #de8f05 orange; never red/green; viridis/plasma/cividis
  for heatmaps), grayscale compatibility via markers and linestyles, minimum font sizes (14pt
  axis labels, 12pt ticks, 16pt title, 12pt legend), minimum line widths, axis labels with units,
  and the ***/**/*/ns significance notation with brackets. CRITICAL: sns.swarmplot SILENTLY DROPS
  points that do not fit (warning "N% of the points cannot be placed") — use stripplot, never
  ship a swarm that dropped data. CRITICAL: palette= without hue= is deprecated in seaborn 0.13 —
  use sns.set_palette(). Plots must never perform new statistical tests: read p_value and
  significance from Statistics_Results.csv.
---

# Publication-Quality Plotting Standards (MANDATORY)

Figures must meet publication standards for Nature, Science, Cell, and other high-impact
journals. Verified against **matplotlib 3.11.0** and **seaborn 0.13.2**.

> **STAGE SEPARATION.** Plotting is STAGE 2. NEVER combine statistics and plotting in
> the same script. Read the values already calculated in STAGE 1 from
> `Statistics_Results.csv`. Do NOT perform new statistical tests here — if the figure
> recomputes a p-value, the figure and the text can silently disagree.

## The two traps that make a figure dishonest

**1. `swarmplot` silently drops points.** If they do not fit, seaborn omits them and
merely warns: `UserWarning: 17.4% of the points cannot be placed`. A swarm is supposed
to be "here is every raw data point" — one that discarded a sixth of the data is a lie.
Watch for the warning; fix it by enlarging the figure, shrinking `size=`, or switching
to `sns.stripplot(..., jitter=0.25, alpha=0.5)`, which never drops points. Above a few
hundred points per group use `stripplot` outright.

**2. `palette=` without `hue=` is deprecated** (seaborn 0.13, removed in 0.14). Use
`sns.set_palette("colorblind")` once, or pass `hue=<x>, legend=False` alongside
`palette=`.

## Image format & quality

1. **RESOLUTION**: Always save at 300 DPI minimum.
   `plt.savefig('plot.png', dpi=300, bbox_inches='tight')` — verified, the PNG reports
   `dpi=(300, 300)`.

2. **FILE FORMATS**: Save in BOTH PNG (viewing, 300 DPI raster) and SVG (editing,
   lossless vector).
   ```python
   plt.savefig('figure.png', dpi=300, bbox_inches='tight')
   plt.savefig('figure.svg', bbox_inches='tight')
   ```

## Color & accessibility

3. **COLOR-BLIND FRIENDLY**: `sns.set_palette('colorblind')`. Verified, the palette is
   `#0173b2, #de8f05, #029e73, #d55e00, #cc78bc, …` — so the two-group standard blue
   `#0173B2` and orange `#DE8F05` are simply its first two entries.
   **NEVER** use red/green combinations. For heatmaps: `'viridis'`, `'plasma'`, `'cividis'`.

4. **GRAYSCALE COMPATIBILITY**: colour alone must never carry the meaning.
   `markers=['o', 's', '^'], linestyles=['-', '--', ':']`

## Typography & legibility

5. **FONT SIZES**: axis labels ≥14pt, tick labels ≥12pt, title ≥16pt, legend ≥12pt.
   Set them once:
   ```python
   plt.rcParams.update({"font.size": 12, "axes.labelsize": 14,
                        "axes.titlesize": 16, "legend.fontsize": 12})
   ```

6. **LINE WIDTHS**: plot lines ≥1.5pt, axis lines ≥1.0pt. `linewidth=2.0`

## Annotations & scale

7. **AXIS LABELS**: always include units — `"Cell Area (μm²)"`, not `"Area"`. If the
   measurement stage never converted, label it `(px²)` honestly.

8. **SCALE INFORMATION**: scale bars on spatial plots; tick labels on everything.

9. **SIGNIFICANCE ANNOTATIONS**: `***` p<0.001, `**` p<0.01, `*` p<0.05, `ns` p≥0.05,
   with brackets connecting the compared groups. Take the p-value **from the CSV**.
   Remember to extend `ylim` afterwards or the bracket is clipped.

## Plot type selection

- **Comparisons**: boxplot with the raw points overlaid (`stripplot`, or `swarmplot`
  only if it places every point).
- **Correlations**: `sns.regplot` (scatter + fit + CI band).
- **Significance**: brackets annotated with p-values from `Statistics_Results.csv`.
- Always `plt.figure(figsize=(8, 6))` or larger.
- A bar chart of means hides the distribution. If you must, overlay the points.

## Coding rules for plotting scripts

- Use the pre-initialized `plt` and `sns` — do NOT re-import them.
- ALWAYS use raw strings for Windows paths: `r'C:\Users\...'`
- ALWAYS `plt.savefig('filename.png', dpi=300, bbox_inches='tight')`, and both PNG + SVG.
- ALWAYS save into the `figures/` subfolder of the project directory.
- If a "PROJECT STATE" section is in your input, use it for the scientific goal (plot
  titles), calibration (axis units μm² not px²), and experimental conditions (group labels).

## Documentation requirement

Your script description MUST include:
- Statistical tests performed and their results
- Plotting parameters (color palette, DPI, file formats)
- Output file locations
- Any data transformations or filtering applied
- Example: "Mann-Whitney U test, p=0.023. Boxplot with swarmplot overlay. Colorblind
  palette. Saved as PNG (300 DPI) and SVG to figures/."

## Verification — fail loudly, not silently

RAISE `ValueError("VERIFICATION FAILED: <what>")` only on conditions ALWAYS true for a
correct run: the PNG and SVG exist and are non-empty; the columns you read exist; the
number of plotted groups equals the number in the CSV; any p-value you read is in [0,1].

Do NOT raise on assumptions about the data. `print("WARNING: ...")` and continue for
small sample sizes, "no significant result" (annotate `ns` — it is publishable), or NaN
values. The one exception: a swarmplot overlap warning is a **defect to fix**, not a
warning to log.

## Files

| File | What it covers |
|---|---|
| `FIGURE_RECIPES.md` | Verified palette hex, the seaborn 0.13 `palette=`/`hue=` deprecation, the swarmplot point-dropping trap, the `scatter_kws` alias collision, the significance-bracket recipe, rcParams |
| `WORKFLOW_BOXPLOT_SIGNIFICANCE.py` | `Statistics_Results.csv` + raw data → boxplot with raw points and a significance bracket → PNG (300 dpi) + SVG. Detects the swarm-overlap warning and redraws as stripplot |
| `WORKFLOW_CORRELATION_PLOT.py` | `Statistics_Results.csv` + raw data → regplot annotated with r and p read from the CSV → PNG + SVG. Switches to a LOWESS fit when Pearson and Spearman disagree |

Both workflows run untouched on synthetic data.
